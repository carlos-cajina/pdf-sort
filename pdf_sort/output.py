"""Output formatters for CLI runs (text + JSON)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from .extract import TransactionInfo

Status = Literal["renamed", "skipped", "error", "unchanged"]


@dataclass
class FileResult:
    """Outcome of processing a single PDF."""
    original: str
    status: Status
    new_name: str | None
    source_bank: str | None
    dest_bank: str | None
    amount: float | None
    date: str | None  # ISO YYYY-MM-DD
    error: str | None


@dataclass
class RunSummary:
    """Aggregate counts for a run."""
    total: int
    renamed: int
    skipped: int
    errors: int
    dry_run: bool
    copied: int = 0
    moved: int = 0


def _iso_date(d: datetime | None) -> str | None:
    if d is None:
        return None
    return d.strftime("%Y-%m-%d")


def result_from_plan_item(
    item: dict,
    status: Status,
    error: str | None = None,
) -> FileResult:
    """Build a FileResult from a deduplicate-plan item."""
    info: TransactionInfo = item["info"]
    return FileResult(
        original=item["original"],
        status=status,
        new_name=item.get("new_name"),
        source_bank=info.source_bank,
        dest_bank=info.dest_bank,
        amount=info.amount,
        date=_iso_date(info.date),
        error=error,
    )


def want_color(no_color_flag: bool) -> bool:
    """Honor --no-color and the NO_COLOR env convention (https://no-color.org)."""
    if no_color_flag:
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return True


def format_text(
    results: list[FileResult],
    summary: RunSummary,
    use_color: bool = True,
) -> str:
    """Human-readable run report."""
    ok = "✓" if use_color else "[OK]"
    warn = "⚠" if use_color else "[WARN]"
    err = "✗" if use_color else "[ERR]"

    lines: list[str] = []
    sep = "=" * 80
    lines.append(sep)
    lines.append("PROPOSED RENAMES:" if summary.dry_run else "RENAMING FILES…")
    lines.append(sep)

    for r in results:
        if r.status == "error":
            lines.append(f"{err} {r.original}: {r.error}")
            lines.append("")
            continue
        if r.new_name is None:
            lines.append(f"{warn} {r.original} — skipped (incomplete info)")
            lines.append("")
            continue
        amt = f"${r.amount:,.2f}" if r.amount is not None else "?"
        dt = r.date or "?"
        lines.append(f"{ok} {r.original}")
        lines.append(f"    → {r.new_name}")
        lines.append(f"      ({r.source_bank} → {r.dest_bank}, {amt}, {dt})")
        lines.append("")

    lines.append(sep)
    if summary.dry_run:
        lines.append("DRY RUN complete. No files were renamed.")
    else:
        lines.append(f"Done! {summary.renamed} file(s) renamed.")
    if summary.copied or summary.moved:
        if summary.copied:
            lines.append(f"  → {summary.copied} file(s) copied to renamed dir")
        if summary.moved:
            lines.append(f"  → {summary.moved} file(s) moved to processed dir")
    lines.append(sep)
    return "\n".join(lines)


def format_json(results: list[FileResult], summary: RunSummary) -> str:
    """Machine-readable run report."""
    return json.dumps(
        {
            "summary": asdict(summary),
            "files": [asdict(r) for r in results],
        },
        indent=2,
        ensure_ascii=False,
    )


def format_output(
    fmt: str,
    results: list[FileResult],
    summary: RunSummary,
    use_color: bool = True,
) -> str:
    """Dispatch to the requested formatter."""
    if fmt == "json":
        return format_json(results, summary)
    return format_text(results, summary, use_color=use_color)
