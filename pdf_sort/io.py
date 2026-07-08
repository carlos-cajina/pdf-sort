"""File I/O operations: copy, sanitize, rename with rollback, archive."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from .types import PlanItem

logger = logging.getLogger(__name__)

_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\s]')


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores."""
    return _SANITIZE_RE.sub("_", name)


def copy_pdfs(
    input_dir: Path,
    output_dir: Path,
    overwrite: bool = True,
    limit: int | None = None,
) -> list[Path]:
    """Copy PDFs from *input_dir* to *output_dir*.

    Returns list of destination paths.
    """
    if not input_dir.exists():
        logger.warning("Input directory does not exist: %s", input_dir)
        return []
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(
        f for f in input_dir.iterdir()
        if f.suffix.lower() == ".pdf"
    )
    if limit is not None:
        pdf_files = pdf_files[:limit]

    if not pdf_files:
        logger.warning("No PDF files found in %s", input_dir)
        return []

    copied: list[Path] = []
    for src in pdf_files:
        safe_name = sanitize_filename(src.name)
        dst = output_dir / safe_name
        if dst.exists() and not overwrite:
            logger.warning(
                "Skipping existing file: %s (use --overwrite to replace)", dst,
            )
            copied.append(dst)
            continue
        shutil.copy2(src, dst)
        logger.debug("Copied %s → %s", src.name, dst.name)
        copied.append(dst)

    logger.info("Copied %d file(s) to %s", len(copied), output_dir)
    return copied


def rename_with_rollback(plan: list[PlanItem], target_dir: Path) -> list[PlanItem]:
    """Rename files according to *plan*.  Rolls back on failure.

    Each item must have ``path`` (current Path) and ``new_name`` (str or None).
    Items with ``new_name=None`` are skipped.  Returned items include
    ``old_path`` and ``new_path``.
    """
    renamed: list[PlanItem] = []

    try:
        for item in plan:
            if item.get("new_name") is None:
                logger.warning("Skipping incomplete record for: %s", item["original"])
                continue
            old_path: Path = item["path"]
            new_path = target_dir / item["new_name"]
            shutil.move(str(old_path), str(new_path))
            logger.info("✓ %s → %s", item["original"], item["new_name"])
            renamed.append({**item, "old_path": old_path, "new_path": new_path})
    except Exception:
        logger.error("Rename failed — rolling back %d file(s)…", len(renamed))
        rollback_errors: list[Exception] = []
        for item in reversed(renamed):
            try:
                shutil.move(str(item["new_path"]), str(item["old_path"]))
                logger.info("Rolled back: %s ← %s", item["original"], item["new_name"])
            except Exception as rb_exc:
                rollback_errors.append(rb_exc)
                logger.error("Rollback failed for %s: %s", item["original"], rb_exc)
        if rollback_errors:
            raise RuntimeError(
                f"Rename failed and {len(rollback_errors)} rollback error(s) occurred"
            ) from rollback_errors[0]
        raise

    return renamed


def _build_source_index(input_dir: Path) -> dict[str, Path]:
    """Build a single name → Path index of all PDFs in *input_dir*.

    M1: O(n) once instead of O(n) per file.  Includes both raw names
    and sanitized names so callers can look up by either.
    """
    index: dict[str, Path] = {}
    for f in input_dir.iterdir():
        if f.suffix.lower() != ".pdf":
            continue
        index[f.name] = f
        sanitized = sanitize_filename(f.name)
        if sanitized != f.name:
            index[sanitized] = f
    return index


def _find_source_in_dir(input_dir: Path, name: str) -> Path | None:
    """Find a PDF in *input_dir* matching *name* (raw or sanitized)."""
    index = _build_source_index(input_dir)
    return index.get(name) or index.get(sanitize_filename(name))


def archive_renamed(
    plan: list[PlanItem],
    renamed_dir: Path,
    dry_run: bool = True,
) -> int:
    """Copy each renamed file to *renamed_dir*.

    Returns number of items archived.  Skips items with no ``new_path``.
    """
    count = 0
    for item in plan:
        if item.get("new_name") is None:
            continue
        renamed_src = item.get("new_path")
        if renamed_src is None:
            continue
        new_name = item["new_name"]
        dst = renamed_dir / new_name
        if dry_run:
            logger.info("  [DRY RUN] Would copy: %s → %s", new_name, dst)
        else:
            renamed_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(renamed_src, dst)
            logger.info("  Copied to renamed: %s", dst.name)
        count += 1
    return count


def move_processed(
    plan: list[PlanItem],
    input_dir: Path,
    processed_dir: Path,
    dry_run: bool = True,
) -> int:
    """Move original source PDFs to *processed_dir*.

    Builds a single source index (M1) for O(1) lookups.  Returns number
    of items moved.
    """
    if not input_dir.exists():
        logger.debug("Input directory missing, nothing to move: %s", input_dir)
        return 0

    index = _build_source_index(input_dir)
    count = 0
    for item in plan:
        if item.get("new_name") is None:
            continue
        src_file = index.get(item["original"]) or index.get(sanitize_filename(item["original"]))
        if src_file is None:
            logger.debug(
                "  Original not found in input dir, skipping move: %s",
                item["original"],
            )
            continue
        dst = processed_dir / src_file.name
        if dry_run:
            logger.info("  [DRY RUN] Would move: %s → %s", src_file.name, dst)
        else:
            processed_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_file), str(dst))
            logger.info("  Moved to processed: %s", src_file.name)
        count += 1
    return count


def archive_processed(
    plan: list[PlanItem],
    input_dir: Path,
    processed_dir: Path | None = None,
    renamed_dir: Path | None = None,
    dry_run: bool = True,
) -> tuple[int, int]:
    """Back-compat shim: run both ``archive_renamed`` and ``move_processed``.

    New code should call those two directly.  This wrapper exists so
    older callers and tests keep working.
    """
    copied = 0
    moved = 0
    if renamed_dir is not None:
        copied = archive_renamed(plan, renamed_dir, dry_run=dry_run)
    if processed_dir is not None:
        moved = move_processed(plan, input_dir, processed_dir, dry_run=dry_run)
    return copied, moved
