"""Shared type definitions for the pdf-sort pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .extract.models import TransactionInfo


class PlanItem(TypedDict, total=False):
    """One unit of work in the rename pipeline.

    Keys are populated in stages:
      1. ``_extract_entries`` sets ``original``, ``path``, ``info``.
      2. ``deduplicate`` adds ``new_name`` (str when ready, None when skipped).
      3. ``rename_with_rollback`` adds ``old_path`` and ``new_path``.
    """

    original: str
    path: Path
    info: TransactionInfo
    new_name: str | None
    old_path: Path
    new_path: Path
