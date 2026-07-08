"""Thin orchestrator that wires the per-bank parsers together."""

from __future__ import annotations

import logging

from .models import TransactionInfo, clean_text
from .parsers import PARSERS, extract_amount, parse_date

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
