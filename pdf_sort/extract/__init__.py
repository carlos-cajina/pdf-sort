"""PDF text extraction logic for Mexican bank transfer receipts.

This package is organized as:
    patterns.py  — all compiled regexes and configuration tables (pure data)
    models.py    — TransactionInfo dataclass + text/bank-name utilities
    parsers.py   — per-bank identification parsers + date/amount parsers
    orchestrator.py — identify_banks dispatcher + extract_info

The public API (this module) re-exports the names callers expect.
"""

from __future__ import annotations

from .models import TransactionInfo, clean_bank_name, clean_text
from .orchestrator import extract_info, identify_banks
from .parsers import extract_amount, parse_date

__all__ = [
    "TransactionInfo",
    "clean_text",
    "clean_bank_name",
    "extract_info",
    "identify_banks",
    "parse_date",
    "extract_amount",
]
