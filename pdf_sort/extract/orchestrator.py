"""Thin orchestrator that wires the per-bank parsers together."""

from __future__ import annotations

import logging

from .models import TransactionInfo, clean_text, clean_bank_name
from .parsers import PARSERS, extract_amount, parse_date
from .patterns import (
    BANK_ALIASES as _BANK_ALIASES,
    BANK_SIGNATURES as _BANK_SIGNATURES,
    _SANTANDER_CLABE_RE,
)

logger = logging.getLogger(__name__)


def identify_banks(text: str) -> tuple[str, str]:
    """Return (source_bank, destination_bank) for a PDF's text."""
    text_upper = text.upper()
    for parser in PARSERS:
        result = parser(text, text_upper)
        if result is not None:
            return result
    return ("UNKNOWN", "UNKNOWN")


def extract_info(text: str) -> TransactionInfo:
    """Extract date, banks, and amount from PDF text."""
    text = clean_text(text)
    dt = parse_date(text)
    source, dest = identify_banks(text)
    amount = extract_amount(text)
    return TransactionInfo(date=dt, source_bank=source, dest_bank=dest, amount=amount)


def extract_clabe(text: str) -> str | None:
    """Extract the identifier that follows ``Número de cuenta CLABE ...``.

    Returns ``None`` when the text contains no CLABE marker at all.
    """
    match = _SANTANDER_CLABE_RE.search(text)
    if match is None:
        return None
    identifier = match.group(1).strip()
    return identifier if identifier else None


def lookup_bank_by_clabe(clabe: str) -> str:
    """Resolve a bank from a CLABE identifier using Banxico bank codes.

    The leading digits of a Mexican CLABE point at a registered institution
    (e.g. ``50`` -> ``Santander``).  Names are normalized through the engine's
    alias table so callers receive the canonical bank name.
    """
    raw = clabe.replace(" ", "").replace("-", "").split("-")[0].strip()
    key = raw.upper()
    santander_prefixes = _BANK_SIGNATURES.get("Santander", {}).get("clabe_prefixes", {})
    if key in santander_prefixes:
        return santander_prefixes[key]
    if key in _BANK_ALIASES:
        return _BANK_ALIASES[key]
    return "UNKNOWN"
