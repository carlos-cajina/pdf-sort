"""Filename building and deduplication logic."""

from __future__ import annotations

import calendar
import logging
from collections import Counter
from datetime import datetime
from .extract import TransactionInfo
from .types import PlanItem

logger = logging.getLogger(__name__)


def fmt_amount(num: float) -> str:
    """Format number in Mexico style: 1,234.56"""
    return f"{num:,.2f}"


def fmt_month_year(d: datetime) -> str:
    """e.g. May2026"""
    return f"{calendar.month_abbr[d.month]}{d.year}"


def build_filename(info: TransactionInfo, suffix: str = "") -> str | None:
    """Build target filename from extracted info.

    Returns None if critical fields are missing (ME-6).
    """
    if not info.is_complete():
        logger.warning(
            "Skipping rename for incomplete record: source=%s, dest=%s, amount=%s, date=%s",
            info.source_bank, info.dest_bank, info.amount, info.date,
        )
        return None

    amount_str = fmt_amount(info.amount)  # type: ignore[arg-type]
    month_str = fmt_month_year(info.date)  # type: ignore[arg-type]
    base = f"transf{info.source_bank}_to_{info.dest_bank}_x{amount_str}_{month_str}"
    if suffix:
        base += f"_{suffix}"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


def deduplicate(plan: list[PlanItem]) -> list[PlanItem]:
    """Assign unique suffixes to colliding target names.

    Pure: returns a new list of new dicts; does not mutate inputs.
    """
    name_counter: Counter[str] = Counter()
    result: list[PlanItem] = []

    for item in plan:
        info: TransactionInfo = item["info"]
        base = build_filename(info)
        if base is None:
            result.append({**item, "new_name": None})
            continue

        name_counter[base] += 1
        count = name_counter[base]
        if count > 1:
            base_no_ext = base.rsplit(".pdf", 1)[0] if base.lower().endswith(".pdf") else base
            result.append({**item, "new_name": f"{base_no_ext}_{count}.pdf"})
        else:
            result.append({**item, "new_name": base})

    return result

