"""PDF text extraction logic for Mexican bank transfer receipts."""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timezone
# ---------------------------------------------------------------------------
MX_TZ: Final = ZoneInfo("America/Mexico_City")

# ---------------------------------------------------------------------------
# Month mappings
# ---------------------------------------------------------------------------
MONTH_MAP_ES: Final[dict[str, int]] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# ---------------------------------------------------------------------------
# Text cleaning: strip U+FFFF and other replacement/corrupt characters (Ph1-1D)
# ---------------------------------------------------------------------------
_STRIP_CORRUPT_RE: Final = re.compile(r"[\uffff\ufffd\x00]")


def _clean_text(text: str) -> str:
    """Remove U+FFFF, U+FFFD, and null bytes from extracted PDF text."""
    return _STRIP_CORRUPT_RE.sub("", text)


# ---------------------------------------------------------------------------
# Compiled regex patterns (ME-5)
# ---------------------------------------------------------------------------
_DATE_DMY_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # 10/May/2026 or 10/may/2026
    (re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # 22/may/26 — 2-digit year (Santander programmed TDC)
    (re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{2})"), "%y"),
    # Fecha de operación 27/abr/2026 (Santander)
    (re.compile(r"Fecha de operación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # Fecha y hora de operación 30/abr/2026 - 04:38:24 h (Santander)
    (re.compile(r"Fecha y hora de operación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # Fecha y hora de operación 22/may/26 - 21:27:42 (Santander programmed, 2-digit year)
    (re.compile(r"Fecha y hora de operación\s+(\d{1,2})/([A-Za-z]{3})/(\d{2})"), "%y"),
    # Fecha y hora de aplicación 27/abr/2026 - 06:10:22 h (Santander)
    (re.compile(r"Fecha y hora de aplicación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # 30 Abr 2026 (Banamex Spanish)
    (re.compile(r"(\d{1,2})\s+(Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)\s+(\d{4})", re.IGNORECASE), "%b"),
    # 30 Apr 2026 (Banamex English)
    (re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
    # Fecha de aplicación: 10 May 2026
    (re.compile(r"Fecha de aplicación:\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
    # Fecha: 14 may, 2026 (AmEx)
    (re.compile(r"Fecha\s*\n(\d{1,2})\s+([A-Za-z]{3}),\s*(\d{4})"), "%b"),
]

_DATE_NUMERIC_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"Fecha de operación:\s*(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"Fecha de operación:\s*(\d{2})-(\d{2})-(\d{4})"),  # Ph1-1B: 22-04-2026 (BBVA SPEI)
    re.compile(r"Fecha de aplicación:\s*(\d{2})-(\d{2})-(\d{4})"),
    re.compile(r"Fecha:\s*(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"(\d{2})-(\d{2})-(\d{4})"),  # Ph1-1B: bare 22-04-2026
]

# Amount patterns — ordered by specificity.  We deliberately omit any
# pattern anchored on "Comisión" to avoid matching fees (CR-3).
# Single-line patterns only (per-line search in pass 2).
_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    # Labeled amounts with decimals
    re.compile(r"Importe a pagar:\s*\$?\s*([\d,]+\.\d{2})"),  # Ph1-1C: BBVA SPEI
    re.compile(r"Importe:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe Pagado:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe del pago en Pesos\s*\n\$?\s*([\d,]+\.\d{2})"),  # Ph2-2A: AmEx
    # Labeled amounts without decimals (Ph1-1A)
    re.compile(r"Importe total \(MXN\)\s*\$?\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Importe Pagado:\s*\$?\s*([\d,]+)(?:\s|$)"),  # Ph1-1A
    re.compile(r"Importe:\s*\$?\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Monto\s*\$?\s*([\d,]+\.\d{2})"),
    # Generic dollar amounts (must come after labeled patterns)
    re.compile(r"\$\s*([\d,]+\.\d{2})"),
    re.compile(r"\$\s*([\d,]+)(?:\s|$)"),  # Ph1-1A: $85, $900 without decimals
]

# Multi-line patterns for full-text search in pass 1.
_MULTILINE_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    # "$600.00\nImporte total" (Santander: amount before label)
    re.compile(r"\$\s*([\d,]+\.\d{2})\s*\nImporte total"),
    # "Importe total (MXN)\n$300.00" (Santander: label before amount)
    re.compile(r"Importe total \(MXN\)\s*\n\$\s*([\d,]+\.\d{2})"),
    # "Importe total (MXN)\n$85" — whole-number (Ph1-1A)
    re.compile(r"Importe total \(MXN\)\s*\n\$\s*([\d,]+)(?:\s|$)"),
    # "Monto\n$3,500.00" (Banamex)
    re.compile(r"Monto\s*\n\$\s*([\d,]+\.\d{2})"),
    # "Importe Pagado:\n$900" — whole-number multi-line (Ph1-1A)
    re.compile(r"Importe Pagado:\s*\n\$\s*([\d,]+)(?:\s|$)"),
    # "Importe Pagado:\n$10,224.01" — with decimals
    re.compile(r"Importe Pagado:\s*\n\$\s*([\d,]+\.\d{2})"),
]

# Bank detection regexes
_BBVA_DEST_RE: Final = re.compile(r"Banco destino:\s*(\S+)", re.IGNORECASE)
_BANAMEX_DEP_RE: Final = re.compile(r"Cuenta de depósito:\s*(.+?)(?:\n|$)")
_BANAMEX_CARD_RE: Final = re.compile(r"Tarjeta de crédito\s*\n?([^\n]+)")
_SANTANDER_TDC_RE: Final = re.compile(r"TDC\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_CLABE_RE: Final = re.compile(r"Número de cuenta\s+CLABE\s+\*\d+\s*-\s*([^\n]+)")
# Ph2-2B: contact info without CLABE keyword (e.g. "Número de cuenta *2832 - Nu Mexico")
_SANTANDER_CONTACT_ACCT_RE: Final = re.compile(r"Número de cuenta\s+\*\d+\s*-\s*([^\n]+)")
# Ph2-2B: "Cuenta *5697 - Santander" (transferencia a terceros Santander)
_SANTANDER_CUENTA_RE: Final = re.compile(r"Cuenta\s+\*\d+\s*-\s*([^\n]+)")
# Ph2-2B: "Tarjeta de débito *4494 - null"
_SANTANDER_DEBITO_RE: Final = re.compile(r"Tarjeta de débito\s+\*\d+\s*-\s*([^\n]+)")
_TRAILING_LETTER_RE: Final = re.compile(r"\s+[A-Z]$")

# ---------------------------------------------------------------------------
# Configurable bank signatures (HI-2)
# ---------------------------------------------------------------------------
BANK_SIGNATURES: Final[dict[str, dict[str, list[str]]]] = {
    "BBVA": {
        "source_markers": ["BBVA", "BANCO DESTINO:"],
        # Ph2-2D: alternative BBVA markers when "BBVA" is not in text
        "alt_markers": [
            ("BANCO DESTINO:", "ENLACE PERSONAL"),
            ("BANCO DESTINO:", "TRANSFERENCIAS A OTROS BANCOS SPEI"),
        ],
        # Ph2-2D: BBVA own-TDC markers (CUENTA DESTINO without BANCO DESTINO)
        "own_tdc_markers": [
            ("BBVA", "CUENTA DESTINO", "TARJETA DE CRÉDITO"),
            ("BBVA", "TIPO DE OPERACIÓN", "TRASPASO CUENTAS PROPIAS"),
        ],
        # Ph1-1D: fuzzy BBVA markers when 'A' chars are corrupted (BBV instead of BBVA)
        # Each tuple is a set of substrings; ALL must appear in the space-stripped text.
        "fuzzy_markers": [
            ("BBV", "CUENT", "DESTINO", "TARJET", "CRÉDITO"),
            ("BBV", "TIPO", "OPER", "TRSPSO", "CUENTS", "PROPIS"),
        ],
        "destination_re": _BBVA_DEST_RE,
    },
    "Banamex": {
        "source_markers": [
            "MI CUENTA BANAMEX",
            "MICUENTA BANAME",
            "CUENTAS BANAMEX",
            "PAGO A TARJETAS BANAMEX",
            "COMPROBANTE DE PAGO DE TARJETAS",
        ],
        "interbank_marker": "PAGO INTERBANCARIO",
    },
    "Santander": {
        "source_markers": ["BANCO SANTANDER"],
        "tdc_other": "PAGO DE TDC A OTROS BANCOS",
        "tdc_own": "PAGO DE TDC PROPIA",
        "transfer": "TRANSFERENCIA ENVIADA",
        # Ph2-2C: ¡Programaste el pago de una tarjeta!
        "programmed_tdc": "PROGRAMASTE EL PAGO DE UNA TARJETA",
    },
    # Ph2-2A: American Express
    "Amex": {
        "source_markers": ["AMERICAN EXPRESS", "CONFIRM PAYMENT"],
        "source_bank_indicator": "SANTANDER",
    },
}

ACRONYMS: Final[set[str]] = {"BBVA", "HSBC", "CIH", "SPEI", "TDC"}

# Common bank aliases found in receipts → canonical short name (HI-2 extension)
BANK_ALIASES: Final[dict[str, str]] = {
    "BBVA MEXICO": "BBVA",
    "BBVA MEX": "BBVA",
    "BBVA BANCOMER": "BBVA",
    "BANAMEX": "Banamex",
    "SANTANDER": "Santander",
    "BANORTE": "Banorte",
    "HSBC": "HSBC",
    "MERCADO PAGO": "MercadoPago",
    "MERCADO PAGO W": "MercadoPago",
    "TDC COSTCO BANAME": "Costco",
    # Ph2-2B: new destination banks
    "NU MEXICO": "NuMexico",
    "NU": "NuMexico",
    "AMERICAN EXPRESS": "Amex",
}


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class TransactionInfo:
    """Extracted metadata from a single transfer receipt."""
    date: datetime | None
    source_bank: str
    dest_bank: str
    amount: float | None

    def is_complete(self) -> bool:
        return self.date is not None and self.amount is not None and self.source_bank != "UNKNOWN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean_bank_name(name: str) -> str:
    """Normalize bank name: resolve aliases, UPPER for acronyms, PascalCase otherwise."""
    # Step 1: resolve known aliases (e.g. "BBVA Mexico" → "BBVA")
    upper_key = name.upper().strip()
    if upper_key in BANK_ALIASES:
        return BANK_ALIASES[upper_key]
    # Step 2: keep acronyms uppercase
    upper = upper_key.replace(" ", "")
    if upper in ACRONYMS:
        return upper
    # Step 3: title-case if uniformly cased, else strip spaces
    if name == name.upper() or name == name.lower():
        return name.title().replace(" ", "")
    return name.replace(" ", "")


def _parse_date_dmy(day_s: str, mon_s: str, year_s: str, fmt: str = "%b") -> datetime | None:
    day = int(day_s)
    mon_lower = mon_s.lower()
    year: int
    if fmt == "%y":
        year = 2000 + int(year_s)
    else:
        year = int(year_s)
    if mon_lower in MONTH_MAP_ES:
        return datetime(year, MONTH_MAP_ES[mon_lower], day, tzinfo=MX_TZ)
    try:
        dt = datetime.strptime(f"{day} {mon_s} {year}", f"%d %b %Y")
        return dt.replace(tzinfo=MX_TZ)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------
def parse_date(text: str) -> datetime | None:
    """Extract a Mexico-City-aware datetime from receipt text."""
    for pattern, fmt in _DATE_DMY_PATTERNS:
        m = pattern.search(text)
        if m:
            result = _parse_date_dmy(m.group(1), m.group(2), m.group(3), fmt)
            if result:
                return result

    for pattern in _DATE_NUMERIC_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                dt = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=MX_TZ)
                return dt
            except ValueError:
                continue
    return None


def _extract_santander_dest(text: str, text_upper: str) -> str | None:
    """Ph2-2B: try multiple regexes to identify the destination from Santander contact info."""
    # Try CLABE first (most specific, for SPEI transfers)
    m = _SANTANDER_CLABE_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        dest_name = _TRAILING_LETTER_RE.sub("", dest_name).strip()
        return _clean_bank_name(dest_name)

    # Try TDC (for credit card payments)
    m = _SANTANDER_TDC_RE.search(text)
    if m:
        bank_name = m.group(1).strip()
        # e.g. "BBVA BANCOMER" → "BBVA"
        first_word = bank_name.split()[0].upper()
        if first_word in ("NULL", "NONE", ""):
            return "OTHER"
        return _clean_bank_name(first_word)

    # Try contact account without CLABE keyword (e.g. "Número de cuenta *2832 - Nu Mexico")
    m = _SANTANDER_CONTACT_ACCT_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        return _clean_bank_name(dest_name)

    # Try "Cuenta *5697 - Santander" (transferencia a terceros)
    m = _SANTANDER_CUENTA_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        return _clean_bank_name(dest_name)

    # Try "Tarjeta de débito *4494 - null"
    m = _SANTANDER_DEBITO_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        first_word = dest_name.split()[0].upper()
        if first_word in ("NULL", "NONE", ""):
            return "OTHER"
        return _clean_bank_name(dest_name)

    return None


def identify_banks(text: str) -> tuple[str, str]:
    """Returns (source_bank, destination_bank)."""
    text_upper = text.upper()

    # --- AmEx detection (Ph2-2A) — check before BBVA/Santander ---
    amex_cfg = BANK_SIGNATURES["Amex"]
    if all(marker in text_upper for marker in amex_cfg["source_markers"]):
        source_indicator = amex_cfg["source_bank_indicator"]
        # Look for e.g. "SANTANDER - 6784" or just "SANTANDER" in text
        if source_indicator in text_upper:
            return (_clean_bank_name(source_indicator), _clean_bank_name("American Express"))
        return ("UNKNOWN", _clean_bank_name("American Express"))

    # --- BBVA source ---
    bbva_cfg = BANK_SIGNATURES["BBVA"]
    is_bbva = all(marker in text_upper for marker in bbva_cfg["source_markers"])

    # Ph2-2D: try alternative BBVA markers when standard markers don't both match
    if not is_bbva:
        # Try alt_markers (e.g. "BANCO DESTINO:" + "ENLACE PERSONAL")
        for alt_pair in bbva_cfg.get("alt_markers", []):
            if all(m in text_upper for m in alt_pair):
                is_bbva = True
                break
    if not is_bbva and "BBVA" in text_upper:
        # Ph2-2D: own-TDC markers (BBVA internal credit card payments)
        for tdc_set in bbva_cfg.get("own_tdc_markers", []):
            if all(m in text_upper for m in tdc_set):
                is_bbva = True
                break
    # Ph1-1D: fuzzy matching when BBVA text is partially corrupted
    # (spaces and 'A' chars may be missing — strip spaces for comparison)
    if not is_bbva:
        text_nospace = text_upper.replace(" ", "")
        for fuzzy_set in bbva_cfg.get("fuzzy_markers", []):
            if all(m.replace(" ", "") in text_nospace for m in fuzzy_set):
                is_bbva = True
                break

    if is_bbva:
        m = _BBVA_DEST_RE.search(text)
        if m:
            dest = m.group(1).strip()
            return (_clean_bank_name("BBVA"), _clean_bank_name(dest))
        # Ph2-2D: own-TDC: destination is also BBVA since it's an own-account payment
        if any(all(m in text_upper for m in tdc_set)
               for tdc_set in bbva_cfg.get("own_tdc_markers", [])):
            return (_clean_bank_name("BBVA"), _clean_bank_name("BBVA"))
        # Ph1-1D: fuzzy own-TDC destination check
        text_nospace = text_upper.replace(" ", "")
        for fuzzy_set in bbva_cfg.get("fuzzy_markers", []):
            if all(m.replace(" ", "") in text_nospace for m in fuzzy_set):
                return (_clean_bank_name("BBVA"), _clean_bank_name("BBVA"))
        return (_clean_bank_name("BBVA"), "OTHER")

    # --- Banamex source ---
    banamex_markers = BANK_SIGNATURES["Banamex"]["source_markers"]
    is_banamex = any(marker in text_upper for marker in banamex_markers)
    if not is_banamex and "PAGO INTERBANCARIO" in text_upper and "BANAMEX" in text_upper:
        is_banamex = True

    if is_banamex:
        source = _clean_bank_name("Banamex")

        m_dep = _BANAMEX_DEP_RE.search(text)
        if m_dep:
            dep_line = m_dep.group(1).strip()
            dep_upper = dep_line.upper()
            for bank in ["SANTANDER", "BANAMEX", "BBVA", "BANORTE", "HSBC", "AZTECA",
                         "INBURSA", "SCOTIABANK", "MERCADO PAGO"]:
                if bank in dep_upper:
                    return (source, _clean_bank_name(bank))
            parts = [p.strip() for p in dep_line.split("-")]
            if len(parts) >= 2 and parts[1].strip():
                return (source, _clean_bank_name(parts[1]))
            return (source, "OTHER")

        if "PAGO A TARJETAS BANAMEX" in text_upper or "COMPROBANTE DE PAGO DE TARJETAS" in text_upper:
            m_card = _BANAMEX_CARD_RE.search(text)
            if m_card:
                card_line = m_card.group(1).strip()
                card_name = card_line.split(".")[0].strip()
                return (source, _clean_bank_name(f"TDC {card_name}" if card_name else "TDC Banamex"))
            return (source, _clean_bank_name("TDC Banamex"))

        if "PAGO INTERBANCARIO" in text_upper:
            return (source, "OTHER")
        return (source, "OTHER")

    # --- Santander source ---
    if "BANCO SANTANDER" in text_upper:
        source = _clean_bank_name("Santander")

        # Ph2-2C: ¡Programaste el pago de una tarjeta!
        if BANK_SIGNATURES["Santander"]["programmed_tdc"] in text_upper:
            dest = _extract_santander_dest(text, text_upper)
            if dest:
                return (source, dest)
            return (source, "OTHER")

        if "PAGO DE TDC A OTROS BANCOS" in text_upper:
            dest = _extract_santander_dest(text, text_upper)
            if dest:
                return (source, dest)
            return (source, "OTHER")

        if "PAGO DE TDC PROPIA" in text_upper:
            return (source, _clean_bank_name("Santander"))

        if "TRANSFERENCIA ENVIADA" in text_upper:
            dest = _extract_santander_dest(text, text_upper)
            if dest:
                return (source, dest)
            return (source, "OTHER")

        # Generic Santander: try contact parsing
        dest = _extract_santander_dest(text, text_upper)
        if dest:
            return (source, dest)
        return (source, "OTHER")

    # Generic fallback (Ph2-2D: don't match SANTANDER if it's in BANCO DESTINO context)
    if "COMPROBANTE DE PAGO DE TARJETAS" in text_upper and "BANAMEX" in text_upper:
        m_card = _BANAMEX_CARD_RE.search(text)
        if m_card:
            card_line = m_card.group(1).strip()
            card_name = card_line.split(".")[0].strip()
            tdc_name = f"TDC {card_name}" if card_name else "TDC Banamex"
            return (_clean_bank_name("Banamex"), _clean_bank_name(tdc_name))
        return (_clean_bank_name("Banamex"), _clean_bank_name("TDC Banamex"))
    if "BANAMEX" in text_upper:
        return (_clean_bank_name("Banamex"), "OTHER")
    # Ph2-2D: only match SANTANDER as source if it's NOT in a "BANCO DESTINO:" context
    # (which would mean it's the destination bank, not the source)
    if "SANTANDER" in text_upper and "BANCO DESTINO:" not in text_upper:
        return (_clean_bank_name("Santander"), "OTHER")

    return ("UNKNOWN", "UNKNOWN")


def extract_amount(text: str) -> float | None:
    """Extract the principal transfer amount in MXN.

    Pass 1 — full-text search for multi-line patterns (e.g. Santander
    where the amount label and value appear on separate lines).

    Pass 2 — per-line search with fee/commission exclusion (CR-3).
    """
    fee_keywords = ("COMISIÓN", "COMISION", "IVA", "COSTO", "IMPUESTO", "FEE")
    label_keywords = ("IMPORTE", "MONTO")

    # ── Pass 1: full-text multi-line patterns ────────────────────────────
    for pattern in _MULTILINE_AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if val >= 0:
                return val

    # ── Pass 2: per-line search with fee exclusion ───────────────────────
    lines = text.splitlines()
    for pattern in _AMOUNT_PATTERNS:
        for i, line in enumerate(lines):
            line_upper = line.upper()
            # Skip lines that are themselves fee/commission lines
            if any(kw in line_upper for kw in fee_keywords):
                continue
            # For unlabeled amount lines (e.g. "$0.00 MXN"), peek at the
            # next line for fee keywords — this catches the Santander
            # layout where "$0.00 MXN" is followed by "Costo de la
            # operación + IVA".  Labeled lines ("Importe: $128.00") are
            # exempt so they are not skipped when the next line is a fee.
            is_labeled = any(kw in line_upper for kw in label_keywords)
            if not is_labeled:
                next_line = lines[i + 1].upper() if i + 1 < len(lines) else ""
                if any(kw in next_line for kw in fee_keywords):
                    continue
            m = pattern.search(line)
            if m:
                amount_str = m.group(1).replace(",", "")
                try:
                    val = float(amount_str)
                    if val >= 0:
                        return val
                except ValueError:
                    continue
    return None


def extract_info(text: str) -> TransactionInfo:
    """Extract all needed info from PDF text.

    Ph1-1D: text is cleaned of U+FFFF/U+FFFD/null chars before processing.
    """
    text = _clean_text(text)
    dt = parse_date(text)
    source, dest = identify_banks(text)
    amount = extract_amount(text)
    return TransactionInfo(date=dt, source_bank=source, dest_bank=dest, amount=amount)
