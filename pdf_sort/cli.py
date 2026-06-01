"""CLI entry point with argparse and logging."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pdfplumber

from .extract import extract_info
from .io import copy_pdfs, rename_with_rollback
from .rename import build_filename, deduplicate

logger = logging.getLogger("pdf_sort")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename Mexican bank-transfer PDF receipts with consistent filenames.",
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
        action="store_true",
        help="Overwrite existing files in output dir when copying",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> list[dict] | None:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)
    dry_run = not args.execute

    input_dir = args.input_dir.expanduser()
    output_dir = args.output_dir.expanduser().resolve()

    # ── Step 1: Copy PDFs ──────────────────────────────────────────────
    copied = copy_pdfs(input_dir, output_dir, overwrite=args.overwrite)
    if not copied:
        logger.info("No PDFs to process.")
        return None

    # ── Step 2: Extract info ───────────────────────────────────────────
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

    # ── Step 3: Build rename plan ───────────────────────────────────────
    plan = deduplicate(entries)

    print()
    print("=" * 80)
    print("PROPOSED RENAMES:" if dry_run else "RENAMING FILES…")
    print("=" * 80)

    skipped = 0
    for p in plan:
        if p["new_name"] is None:
            logger.warning("⚠ %s — skipped (incomplete info)", p["original"])
            skipped += 1
            continue
        amt = f"${p['info'].amount:,.2f}" if p["info"].amount else "?"
        dt = p["info"].date.strftime("%d %b %Y") if p["info"].date else "?"
        print(f"  {p['original']}")
        print(f"    → {p['new_name']}")
        print(f"      ({p['info'].source_bank} → {p['info'].dest_bank}, {amt}, {dt})")
        print()

    if skipped:
        print(f"  ⚠ {skipped} file(s) skipped due to incomplete extraction.\n")

    # ── Step 4: Execute or dry-run ──────────────────────────────────────
    if dry_run:
        print("=" * 80)
        print("DRY RUN complete. No files were renamed.")
        print("=" * 80)
        print("\nTo proceed with actual renaming, run:")
        print("  python3 -m pdf_sort.cli --execute\n")
        return plan

    print("=" * 80)
    print("RENAMING FILES…")
    print("=" * 80)
    renamed = rename_with_rollback(plan, output_dir)
    print(f"\nDone! {len(renamed)} file(s) renamed.")
    if skipped:
        print(f"  ({skipped} file(s) skipped due to incomplete extraction)")
    return plan