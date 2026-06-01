"""File I/O operations: copy, sanitize, rename with rollback."""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

# Path sanitization (LO-2)
_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\s]')


def sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters with underscores."""
    return _SANITIZE_RE.sub("_", name)


def copy_pdfs(input_dir: Path, output_dir: Path, overwrite: bool = True) -> list[Path]:
    """Copy all PDFs from *input_dir* to *output_dir*.

    Returns list of destination paths.  (CR-2 fix: warn on collision,
    overwrite by default.)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_files = sorted(
        f for f in input_dir.iterdir()
        if f.suffix.lower() == ".pdf"
    )

    if not pdf_files:
        logger.warning("No PDF files found in %s", input_dir)
        return []

    copied: list[Path] = []
    for src in pdf_files:
        safe_name = sanitize_filename(src.name)
        dst = output_dir / safe_name
        if dst.exists() and not overwrite:
            logger.warning("Skipping existing file: %s (use --overwrite to replace)", dst)
            copied.append(dst)
            continue
        shutil.copy2(src, dst)
        logger.debug("Copied %s → %s", src.name, dst.name)
        copied.append(dst)

    logger.info("Copied %d file(s) to %s", len(copied), output_dir)
    return copied


def rename_with_rollback(plan: list[dict], target_dir: Path) -> list[dict]:
    """Rename files according to *plan*.  Rolls back on failure (HI-4).

    Each item in *plan* must have keys: ``path`` (current Path) and
    ``new_name`` (str or None).  Items with ``new_name=None`` are skipped.
    """
    renamed: list[dict] = []

    try:
        for item in plan:
            if item["new_name"] is None:
                logger.warning("Skipping incomplete record for: %s", item["original"])
                continue
            old_path: Path = item["path"]
            new_path = target_dir / item["new_name"]
            old_path.rename(new_path)
            logger.info("✓ %s → %s", item["original"], item["new_name"])
            renamed.append({**item, "old_path": old_path, "new_path": new_path})
    except Exception:
        logger.error("Rename failed — rolling back %d file(s)…", len(renamed))
        for item in reversed(renamed):
            item["new_path"].rename(item["old_path"])
            logger.info("Rolled back: %s ← %s", item["original"], item["new_name"])
        raise

    return renamed


def _find_source_in_dir(input_dir: Path, sanitized_name: str) -> Path | None:
    """Find the real source PDF in *input_dir* whose sanitized name
    matches *sanitized_name*.  Returns None if no match."""
    # Fast path: direct match (must be a .pdf)
    direct = input_dir / sanitized_name
    if direct.exists() and direct.suffix.lower() == ".pdf":
        return direct
    # Slow path: scan for PDFs whose sanitized name matches
    for f in input_dir.iterdir():
        if f.suffix.lower() == ".pdf" and sanitize_filename(f.name) == sanitized_name:
            return f
    return None


def archive_processed(
    plan: list[dict],
    input_dir: Path,
    processed_dir: Path | None = None,
    renamed_dir: Path | None = None,
    dry_run: bool = True,
) -> tuple[int, int]:
    """Post-rename archival: copy renamed files to *renamed_dir* and
    move successfully processed source files from *input_dir* to *processed_dir*.

    Returns (num_copied_to_renamed, num_moved_to_processed).
    """
    copied = 0
    moved = 0

    for item in plan:
        if item.get("new_name") is None:
            continue

        original_name = item["original"]
        new_name = item["new_name"]
        # The renamed file lives at new_path (set by rename_with_rollback)
        renamed_src = item.get("new_path")

        # ── Copy renamed file to renamed_dir ───────────────────────
        if renamed_dir is not None and renamed_src is not None:
            renamed_dir.mkdir(parents=True, exist_ok=True)
            dst = renamed_dir / new_name
            if dry_run:
                logger.info("  [DRY RUN] Would copy: %s → %s", new_name, dst)
            else:
                shutil.copy2(renamed_src, dst)
                logger.info("  Copied to renamed: %s", dst.name)
            copied += 1

        # ── Move original from input_dir to processed_dir ──────────
        if processed_dir is not None:
            src_file = _find_source_in_dir(input_dir, original_name)
            if src_file is not None:
                processed_dir.mkdir(parents=True, exist_ok=True)
                dst = processed_dir / src_file.name
                if dry_run:
                    logger.info("  [DRY RUN] Would move: %s → %s", src_file.name, dst)
                else:
                    shutil.move(str(src_file), str(dst))
                    logger.info("  Moved to processed: %s", src_file.name)
                moved += 1
            else:
                logger.debug("  Original not found in input dir, skipping move: %s", original_name)

    return copied, moved