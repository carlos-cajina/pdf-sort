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
# Compiled regex patterns (ME-5)
# ---------------------------------------------------------------------------
_DATE_DMY_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # 10/May/2026 or 10/may/2026
    (re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # Fecha de operación 27/abr/2026 (Santander)
    (re.compile(r"Fecha de operación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # Fecha y hora de operación 30/abr/2026 - 04:38:24 h (Santander)
    (re.compile(r"Fecha y hora de operación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # Fecha y hora de aplicación 27/abr/2026 - 06:10:22 h (Santander)
    (re.compile(r"Fecha y hora de aplicación\s+(\d{1,2})/([A-Za-z]{3})/(\d{4})"), "%b"),
    # 30 Abr 2026 (Banamex Spanish)
    (re.compile(r"(\d{1,2})\s+(Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)\s+(\d{4})", re.IGNORECASE), "%b"),
    # 30 Apr 2026 (Banamex English)
    (re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
    # Fecha de aplicación: 10 May 2026
    (re.compile(r"Fecha de aplicación:\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
]

_DATE_NUMERIC_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"Fecha de operación:\s*(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"Fecha:\s*(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"(\d{2})/(\d{2})/(\d{4})"),
]

# Amount patterns — ordered by specificity.  We deliberately omit any
# pattern anchored on "Comisión" to avoid matching fees (CR-3).
# Single-line patterns only (per-line search in pass 2).
_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"Importe:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Monto\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"\$\s*([\d,]+\.\d{2})"),
]

# Multi-line patterns for full-text search in pass 1.
_MULTILINE_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    # "$600.00\nImporte total" (Santander: amount before label)
    re.compile(r"\$\s*([\d,]+\.\d{2})\s*\nImporte total"),
    # "Importe total (MXN)\n$300.00" (Santander: label before amount)
    re.compile(r"Importe total \(MXN\)\s*\n\$\s*([\d,]+\.\d{2})"),
    # "Monto\n$3,500.00" (Banamex)
    re.compile(r"Monto\s*\n\$\s*([\d,]+\.\d{2})"),
]

# Bank detection regexes
_BBVA_DEST_RE: Final = re.compile(r"Banco destino:\s*(\S+)", re.IGNORECASE)
_BANAMEX_DEP_RE: Final = re.compile(r"Cuenta de depósito:\s*(.+?)(?:\n|$)")
_BANAMEX_CARD_RE: Final = re.compile(r"Tarjeta de crédito\s*\n?([^\n]+)")
_SANTANDER_TDC_RE: Final = re.compile(r"TDC\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_CLABE_RE: Final = re.compile(r"Número de cuenta\s+CLABE\s+\*\d+\s*-\s*([^\n]+)")
_TRAILING_LETTER_RE: Final = re.compile(r"\s+[A-Z]$")

# ---------------------------------------------------------------------------
# Configurable bank signatures (HI-2)
# ---------------------------------------------------------------------------
BANK_SIGNATURES: Final[dict[str, dict[str, list[str]]]] = {
    "BBVA": {
        "source_markers": ["BBVA", "BANCO DESTINO:"],
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


def _parse_date_dmy(day_s: str, mon_s: str, year_s: str) -> datetime | None:
    day = int(day_s)
    year = int(year_s)
    mon_lower = mon_s.lower()
    if mon_lower in MONTH_MAP_ES:
        return datetime(year, MONTH_MAP_ES[mon_lower], day, tzinfo=MX_TZ)
    try:
        dt = datetime.strptime(f"{day} {mon_s} {year}", "%d %b %Y")
        return dt.replace(tzinfo=MX_TZ)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Extraction functions
# ---------------------------------------------------------------------------
def parse_date(text: str) -> datetime | None:
    """Extract a Mexico-City-aware datetime from receipt text."""
    for pattern, _ in _DATE_DMY_PATTERNS:
        m = pattern.search(text)
        if m:
            result = _parse_date_dmy(m.group(1), m.group(2), m.group(3))
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


def identify_banks(text: str) -> tuple[str, str]:
    """Returns (source_bank, destination_bank)."""
    text_upper = text.upper()

    # --- BBVA source ---
    if all(marker in text_upper for marker in BANK_SIGNATURES["BBVA"]["source_markers"]):
        m = _BBVA_DEST_RE.search(text)
        dest = m.group(1).strip() if m else "OTHER"
        return (_clean_bank_name("BBVA"), _clean_bank_name(dest))

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

        if "PAGO DE TDC A OTROS BANCOS" in text_upper:
            m_tdc = _SANTANDER_TDC_RE.search(text)
            if m_tdc:
                bank_name = m_tdc.group(1).strip().split()[0].upper()
                return (source, _clean_bank_name(bank_name))
            return (source, "OTHER")

        if "PAGO DE TDC PROPIA" in text_upper:
            return (source, _clean_bank_name("Santander"))

        if "TRANSFERENCIA ENVIADA" in text_upper:
            m_clabe = _SANTANDER_CLABE_RE.search(text)
            if m_clabe:
                dest_name = m_clabe.group(1).strip()
                dest_name = dest_name.split("-")[0].strip()
                dest_name = _TRAILING_LETTER_RE.sub("", dest_name).strip()
                return (source, _clean_bank_name(dest_name))
            return (source, "OTHER")

        return (source, "OTHER")

    # Generic fallback
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
    if "SANTANDER" in text_upper:
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
    """Extract all needed info from PDF text."""
    dt = parse_date(text)
    source, dest = identify_banks(text)
    amount = extract_amount(text)
    return TransactionInfo(date=dt, source_bank=source, dest_bank=dest, amount=amount)
