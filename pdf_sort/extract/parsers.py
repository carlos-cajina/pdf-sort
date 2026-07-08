"""Date, amount, and per-bank identification parsers.

Per-bank parsers all share the same signature:

    parse(text: str, text_upper: str) -> tuple[str, str] | None

Returning ``None`` means "this isn't my bank — let the next parser try".
Returning a tuple is a definitive identification.

The orchestrator (``orchestrator.identify_banks``) calls each parser in
priority order and returns the first non-``None`` result.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, Final

from .models import clean_bank_name
from .patterns import (
    MONTH_MAP_ES,
    MX_TZ,
    _AMOUNT_PATTERNS,
    _BANAMEX_CARD_RE,
    _BANAMEX_DEP_RE,
    _BBVA_DEST_RE,
    _DATE_DMY_PATTERNS,
    _DATE_NUMERIC_PATTERNS,
    _MULTILINE_AMOUNT_PATTERNS,
    _SANTANDER_CLABE_RE,
    _SANTANDER_CONTACT_ACCT_RE,
    _SANTANDER_CUENTA_RE,
    _SANTANDER_DEBITO_RE,
    _SANTANDER_TDC_RE,
    _TRAILING_LETTER_RE,
    BANK_SIGNATURES,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------
def _parse_date_dmy(day_s: str, mon_s: str, year_s: str, fmt: str = "%b") -> datetime | None:
    day = int(day_s)
    mon_lower = mon_s.lower()
    if fmt == "%y":
        y = int(year_s)
        # Receipts from 1990s use 50-99, 2000s+ use 00-49
        year = 2000 + y if y < 50 else 1900 + y
    else:
        year = int(year_s)
    if mon_lower in MONTH_MAP_ES:
        return datetime(year, MONTH_MAP_ES[mon_lower], day, tzinfo=MX_TZ)
    try:
        dt = datetime.strptime(f"{day} {mon_s} {year}", f"%d %b %Y")
        return dt.replace(tzinfo=MX_TZ)
    except ValueError:
        return None


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
                return datetime(
                    int(m.group(3)),
                    int(m.group(2)),
                    int(m.group(1)),
                    tzinfo=MX_TZ,
                )
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------
def extract_amount(text: str) -> float | None:
    """Extract the principal transfer amount in MXN.

    Pass 1: full-text multi-line patterns (e.g. Santander label/value
    on separate lines).
    Pass 2: per-line patterns with fee/commission exclusion.
    """
    fee_keywords = ("COMISIÓN", "COMISION", "IVA", "COSTO", "IMPUESTO", "FEE")
    label_keywords = ("IMPORTE", "MONTO")

    for pattern in _MULTILINE_AMOUNT_PATTERNS:
        m = pattern.search(text)
        if m:
            val = float(m.group(1).replace(",", ""))
            if val >= 0:
                return val

    lines = text.splitlines()
    for pattern in _AMOUNT_PATTERNS:
        for i, line in enumerate(lines):
            line_upper = line.upper()
            if any(kw in line_upper for kw in fee_keywords):
                continue
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


# ---------------------------------------------------------------------------
# Santander destination helpers
# ---------------------------------------------------------------------------
def _extract_santander_dest(text: str, text_upper: str) -> str | None:
    """Try multiple regexes to identify the destination from Santander contact info."""
    m = _SANTANDER_CLABE_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        dest_name = _TRAILING_LETTER_RE.sub("", dest_name).strip()
        return clean_bank_name(dest_name)

    m = _SANTANDER_TDC_RE.search(text)
    if m:
        bank_name = m.group(1).strip()
        first_word = bank_name.split()[0].upper()
        if first_word in ("NULL", "NONE", ""):
            return "OTHER"
        return clean_bank_name(first_word)

    m = _SANTANDER_CONTACT_ACCT_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        return clean_bank_name(dest_name)

    m = _SANTANDER_CUENTA_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        dest_name = dest_name.split("-")[0].strip()
        return clean_bank_name(dest_name)

    m = _SANTANDER_DEBITO_RE.search(text)
    if m:
        dest_name = m.group(1).strip()
        first_word = dest_name.split()[0].upper()
        if first_word in ("NULL", "NONE", ""):
            return "OTHER"
        return clean_bank_name(dest_name)

    return None


# ---------------------------------------------------------------------------
# Per-bank parsers
# ---------------------------------------------------------------------------
def _parse_amex(text: str, text_upper: str) -> tuple[str, str] | None:
    cfg = BANK_SIGNATURES["Amex"]
    if not all(marker in text_upper for marker in cfg["source_markers"]):
        return None
    indicator = cfg["source_bank_indicator"]
    if indicator in text_upper:
        return (clean_bank_name(indicator), clean_bank_name("American Express"))
    return ("UNKNOWN", clean_bank_name("American Express"))


def _parse_bbva(text: str, text_upper: str) -> tuple[str, str] | None:
    cfg = BANK_SIGNATURES["BBVA"]
    is_bbva = all(marker in text_upper for marker in cfg["source_markers"])

    if not is_bbva:
        for alt_pair in cfg.get("alt_markers", []):
            if all(m in text_upper for m in alt_pair):
                is_bbva = True
                break

    if not is_bbva and "BBVA" in text_upper:
        for tdc_set in cfg.get("own_tdc_markers", []):
            if all(m in text_upper for m in tdc_set):
                is_bbva = True
                break

    if not is_bbva:
        text_nospace = text_upper.replace(" ", "")
        for fuzzy_set in cfg.get("fuzzy_markers", []):
            if all(m.replace(" ", "") in text_nospace for m in fuzzy_set):
                logger.warning(
                    "BBVA matched via fuzzy markers (corrupted text): %s", fuzzy_set,
                )
                is_bbva = True
                break

    if not is_bbva:
        return None

    m = _BBVA_DEST_RE.search(text)
    if m:
        dest = m.group(1).strip()
        return (clean_bank_name("BBVA"), clean_bank_name(dest))

    if any(all(m in text_upper for m in tdc_set)
           for tdc_set in cfg.get("own_tdc_markers", [])):
        return (clean_bank_name("BBVA"), clean_bank_name("BBVA"))

    text_nospace = text_upper.replace(" ", "")
    for fuzzy_set in cfg.get("fuzzy_markers", []):
        if all(m.replace(" ", "") in text_nospace for m in fuzzy_set):
            logger.warning(
                "BBVA own-TDC matched via fuzzy markers: %s", fuzzy_set,
            )
            return (clean_bank_name("BBVA"), clean_bank_name("BBVA"))

    return (clean_bank_name("BBVA"), "OTHER")


def _parse_banamex(text: str, text_upper: str) -> tuple[str, str] | None:
    cfg = BANK_SIGNATURES["Banamex"]
    is_banamex = any(marker in text_upper for marker in cfg["source_markers"])
    if not is_banamex and "PAGO INTERBANCARIO" in text_upper and "BANAMEX" in text_upper:
        is_banamex = True
    if not is_banamex:
        return None

    source = clean_bank_name("Banamex")

    m_dep = _BANAMEX_DEP_RE.search(text)
    if m_dep:
        dep_line = m_dep.group(1).strip()
        dep_upper = dep_line.upper()
        for bank in [
            "SANTANDER", "BANAMEX", "BBVA", "BANORTE", "HSBC", "AZTECA",
            "INBURSA", "SCOTIABANK", "MERCADO PAGO",
        ]:
            if bank in dep_upper:
                return (source, clean_bank_name(bank))
        parts = [p.strip() for p in dep_line.split("-")]
        if len(parts) >= 2 and parts[1].strip():
            return (source, clean_bank_name(parts[1]))
        return (source, "OTHER")

    if (
        "PAGO A TARJETAS BANAMEX" in text_upper
        or "COMPROBANTE DE PAGO DE TARJETAS" in text_upper
    ):
        m_card = _BANAMEX_CARD_RE.search(text)
        if m_card:
            card_line = m_card.group(1).strip()
            card_name = card_line.split(".")[0].strip()
            tdc = f"TDC {card_name}" if card_name else "TDC Banamex"
            return (source, clean_bank_name(tdc))
        return (source, clean_bank_name("TDC Banamex"))

    if "PAGO INTERBANCARIO" in text_upper:
        return (source, "OTHER")
    return (source, "OTHER")


def _parse_santander(text: str, text_upper: str) -> tuple[str, str] | None:
    if "BANCO SANTANDER" not in text_upper:
        return None
    source = clean_bank_name("Santander")
    cfg = BANK_SIGNATURES["Santander"]

    if cfg["programmed_tdc"] in text_upper:
        dest = _extract_santander_dest(text, text_upper)
        return (source, dest or "OTHER")

    if "PAGO DE TDC A OTROS BANCOS" in text_upper:
        dest = _extract_santander_dest(text, text_upper)
        return (source, dest or "OTHER")

    if "PAGO DE TDC PROPIA" in text_upper:
        return (source, clean_bank_name("Santander"))

    if "TRANSFERENCIA ENVIADA" in text_upper:
        dest = _extract_santander_dest(text, text_upper)
        return (source, dest or "OTHER")

    dest = _extract_santander_dest(text, text_upper)
    if dest:
        return (source, dest)
    return (source, "OTHER")


def _parse_generic(text: str, text_upper: str) -> tuple[str, str] | None:
    """Fallback for receipts without clear source markers."""
    if "COMPROBANTE DE PAGO DE TARJETAS" in text_upper and "BANAMEX" in text_upper:
        m_card = _BANAMEX_CARD_RE.search(text)
        if m_card:
            card_line = m_card.group(1).strip()
            card_name = card_line.split(".")[0].strip()
            tdc = f"TDC {card_name}" if card_name else "TDC Banamex"
            return (clean_bank_name("Banamex"), clean_bank_name(tdc))
        return (clean_bank_name("Banamex"), clean_bank_name("TDC Banamex"))
    if "BANAMEX" in text_upper:
        return (clean_bank_name("Banamex"), "OTHER")
    if "SANTANDER" in text_upper and "BANCO DESTINO:" not in text_upper:
        return (clean_bank_name("Santander"), "OTHER")
    return None


# Ordered dispatch list — first non-None wins.
PARSERS: Final[list[Callable[[str, str], tuple[str, str] | None]]] = [
    _parse_amex,
    _parse_bbva,
    _parse_banamex,
    _parse_santander,
    _parse_generic,
]
