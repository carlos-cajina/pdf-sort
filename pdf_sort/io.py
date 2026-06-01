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