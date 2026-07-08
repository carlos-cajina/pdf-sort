"""Data model and low-level text utilities."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from .patterns import ACRONYMS, BANK_ALIASES, _STRIP_CORRUPT_RE


@dataclass(frozen=True, slots=True)
class TransactionInfo:
    """Extracted metadata from a single transfer receipt."""

    date: datetime | None
    source_bank: str
    dest_bank: str
    amount: float | None

    def is_complete(self) -> bool:
        return (
            self.date is not None
            and self.amount is not None
            and self.source_bank != "UNKNOWN"
        )


def clean_text(text: str) -> str:
    """Remove U+FFFF, U+FFFD, and null bytes from extracted PDF text."""
    return _STRIP_CORRUPT_RE.sub("", text)


def clean_bank_name(name: str) -> str:
    """Normalize bank name: resolve aliases, UPPER for acronyms, PascalCase otherwise."""
    upper_key = name.upper().strip()
    if upper_key in BANK_ALIASES:
        return BANK_ALIASES[upper_key]
    upper = upper_key.replace(" ", "")
    if upper in ACRONYMS:
        return upper
    if name == name.upper() or name == name.lower():
        return name.title().replace(" ", "")
    return name.replace(" ", "")
