"""CLI entry point with argparse and logging."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pdfplumber

from . import __version__
from .extract import extract_info
from .interactive import filter_plan_interactive
from .io import copy_pdfs, rename_with_rollback, archive_processed
from .output import (
    FileResult,
    RunSummary,
    format_output,
    result_from_plan_item,
    want_color,
)
from .rename import deduplicate

logger = logging.getLogger("pdf_sort")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pdf-sort",
        description="Rename Mexican bank-transfer PDF receipts with consistent filenames.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pdf-sort {__version__}",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files (default is dry-run)",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("~/Downloads"),
        help="Directory containing source PDFs (default: ~/Downloads)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory to copy PDFs into and rename (default: current dir)",
    )
    parser.add_argument(
        "--overwrite",
        dest="overwrite",
        action="store_true",
        default=True,
        help="Overwrite existing files in output dir (default: True; use --no-overwrite to skip)",
    )
    parser.add_argument(
        "--no-overwrite",
        dest="overwrite",
        action="store_false",
        help="Skip files that already exist in output dir",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=None,
        help="Move successfully processed source PDFs into this directory",
    )
    parser.add_argument(
        "--renamed-dir",
        type=Path,
        default=None,
        help="Copy renamed PDFs into this directory",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N files (default: all)",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for confirmation before each rename (execute mode only)",
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        help="Strip unicode status markers and use ASCII labels",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args(argv)


def _extract_entries(copied: list[Path]) -> list[dict]:
    """Open each PDF and build a plan entry.  Logs per-file status."""
    entries: list[dict] = []
    for path in copied:
        try:
            with pdfplumber.open(path) as pdf:
                full_text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
        except Exception as exc:
            logger.error("✗ %s: ERROR reading PDF: %s", path.name, exc)
            continue

        info = extract_info(full_text)
        entries.append({
            "original": path.name,
            "path": path,
            "info": info,
        })

        status = "✓" if info.is_complete() else "⚠"
        amt = f"${info.amount:,.2f}" if info.amount is not None else "NOT FOUND"
        dt = info.date.strftime("%d %b %Y") if info.date else "NOT FOUND"
        logger.info("%s %s", status, path.name)
        logger.info("    Source: %s  →  Dest: %s", info.source_bank, info.dest_bank)
        logger.info("    Amount: %s", amt)
        logger.info("    Date:   %s", dt)
    return entries


def _build_results(plan: list[dict]) -> tuple[list[FileResult], int, int]:
    """Convert plan items to FileResult objects; return (results, renamed, skipped)."""
    results: list[FileResult] = []
    renamed = 0
    skipped = 0
    for item in plan:
        if item.get("new_name") is None:
            results.append(result_from_plan_item(item, status="skipped"))
            skipped += 1
        else:
            results.append(result_from_plan_item(item, status="renamed"))
            renamed += 1
    return results, renamed, skipped


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)
    dry_run = not args.execute
    use_color = want_color(args.no_color)

    input_dir = args.input_dir.expanduser()
    output_dir = args.output_dir.expanduser().resolve()
    processed_dir = args.processed_dir.expanduser().resolve() if args.processed_dir else None
    renamed_dir = args.renamed_dir.expanduser().resolve() if args.renamed_dir else None

    # ── Step 1: Copy PDFs ──────────────────────────────────────────────
    copied = copy_pdfs(input_dir, output_dir, overwrite=args.overwrite, limit=args.limit)
    if not copied:
        logger.info("No PDFs to process.")
        summary = RunSummary(total=0, renamed=0, skipped=0, errors=0, dry_run=dry_run)
        print(format_output(args.fmt, [], summary, use_color=use_color))
        return 0

    # ── Step 2: Extract info ───────────────────────────────────────────
    entries = _extract_entries(copied)

    # ── Step 3: Build rename plan ───────────────────────────────────────
    plan = deduplicate(entries)
    results, renamed_count, skipped_count = _build_results(plan)

    # ── Step 4: Execute or dry-run ──────────────────────────────────────
    copied_count = 0
    moved_count = 0

    if dry_run:
        summary = RunSummary(
            total=len(plan), renamed=renamed_count, skipped=skipped_count,
            errors=0, dry_run=True,
        )
        print(format_output(args.fmt, results, summary, use_color=use_color))
        if args.fmt == "text" and (processed_dir or renamed_dir):
            print()
            print("=" * 80)
            print("[DRY RUN] Would also:")
            print("=" * 80)
            if renamed_dir:
                print(f"  Copy renamed files to: {renamed_dir}/")
            if processed_dir:
                print(f"  Move processed originals to: {processed_dir}/")
        return 0 if skipped_count == 0 else 1

    # ── Execute ────────────────────────────────────────────────────────
    if args.interactive:
        plan = filter_plan_interactive(plan)
        # Rebuild results from filtered plan (preserve status, drop rejected)
        results, renamed_count, _ = _build_results(plan)

    renamed = rename_with_rollback(plan, output_dir)

    # ── Step 5: Archive ────────────────────────────────────────────────
    if processed_dir or renamed_dir:
        copied_count, moved_count = archive_processed(
            renamed, input_dir,
            processed_dir=processed_dir,
            renamed_dir=renamed_dir,
            dry_run=False,
        )

    summary = RunSummary(
        total=len(plan), renamed=len(renamed), skipped=skipped_count,
        errors=0, dry_run=False,
        copied=copied_count, moved=moved_count,
    )
    print(format_output(args.fmt, results, summary, use_color=use_color))
    return 0 if skipped_count == 0 else 1
