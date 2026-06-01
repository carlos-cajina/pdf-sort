"""Unit tests for pdf_sort.io module."""

import pytest
import tempfile
from pathlib import Path

from pdf_sort.io import sanitize_filename, copy_pdfs, archive_processed, _find_source_in_dir


class TestFindSourceInDir:
    def test_direct_match(self, tmp_path):
        d = tmp_path / "src"
        d.mkdir()
        (d / "simple.pdf").write_text("x")
        result = _find_source_in_dir(d, "simple.pdf")
        assert result is not None
        assert result.name == "simple.pdf"

    def test_sanitized_match(self, tmp_path):
        """Find a file with spaces in name by its sanitized form."""
        d = tmp_path / "src"
        d.mkdir()
        (d / "My File.pdf").write_text("x")
        # sanitize_filename("My File.pdf") → "My_File.pdf"
        result = _find_source_in_dir(d, "My_File.pdf")
        assert result is not None
        assert result.name == "My File.pdf"

    def test_not_found(self, tmp_path):
        d = tmp_path / "src"
        d.mkdir()
        result = _find_source_in_dir(d, "nonexistent.pdf")
        assert result is None

    def test_ignores_non_pdf(self, tmp_path):
        d = tmp_path / "src"
        d.mkdir()
        (d / "file.txt").write_text("x")
        result = _find_source_in_dir(d, "file.txt")
        assert result is None


class TestSanitizeFilename:
    def test_colons_replaced(self):
        assert sanitize_filename("https:bancanet.banamex.com:apps:.pdf.pdf") == \
            "https_bancanet.banamex.com_apps_.pdf.pdf"

    def test_spaces_replaced(self):
        assert sanitize_filename("my file.pdf") == "my_file.pdf"

    def test_special_chars_replaced(self):
        assert sanitize_filename('file<>:"/\\|?*.pdf') == "file_________.pdf"

    def test_clean_filename_unchanged(self):
        assert sanitize_filename("simple.pdf") == "simple.pdf"


class TestCopyPdfs:
    def test_copies_pdf_files(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        (src / "a.pdf").write_text("pdf-a")
        (src / "b.pdf").write_text("pdf-b")
        (src / "c.txt").write_text("not-pdf")

        result = copy_pdfs(src, dst)
        assert len(result) == 2
        assert (dst / "a.pdf").exists()
        assert (dst / "b.pdf").exists()
        assert not (dst / "c.txt").exists()

    def test_overwrite_existing(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        (src / "a.pdf").write_text("new-content")
        dst.mkdir()
        (dst / "a.pdf").write_text("old-content")

        copy_pdfs(src, dst, overwrite=True)
        assert (dst / "a.pdf").read_text() == "new-content"

    def test_skip_existing_no_overwrite(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()
        (src / "a.pdf").write_text("new-content")
        dst.mkdir()
        (dst / "a.pdf").write_text("old-content")

        copy_pdfs(src, dst, overwrite=False)
        assert (dst / "a.pdf").read_text() == "old-content"

    def test_empty_source(self, tmp_path):
        src = tmp_path / "src"
        dst = tmp_path / "dst"
        src.mkdir()

        result = copy_pdfs(src, dst)
        assert result == []


class TestArchiveProcessed:
    def test_copies_to_renamed_dir(self, tmp_path):
        """Renamed files are copied to renamed_dir."""
        input_dir = tmp_path / "input"
        working_dir = tmp_path / "working"
        renamed_dir = tmp_path / "renamed"
        input_dir.mkdir()
        working_dir.mkdir()

        # Create a source file and a "renamed" copy in working dir
        (input_dir / "source.pdf").write_text("content")
        renamed_path = working_dir / "transfBBVA_to_Banamex_x128.00_May2026.pdf"
        renamed_path.write_text("content")

        plan = [{
            "original": "source.pdf",
            "new_name": "transfBBVA_to_Banamex_x128.00_May2026.pdf",
            "new_path": renamed_path,
        }]

        copied, moved = archive_processed(
            plan, input_dir,
            renamed_dir=renamed_dir,
            dry_run=False,
        )
        assert copied == 1
        assert (renamed_dir / "transfBBVA_to_Banamex_x128.00_May2026.pdf").exists()

    def test_moves_source_to_processed_dir(self, tmp_path):
        """Successfully processed source files are moved to processed_dir."""
        input_dir = tmp_path / "input"
        working_dir = tmp_path / "working"
        processed_dir = tmp_path / "processed"
        input_dir.mkdir()
        working_dir.mkdir()

        (input_dir / "source.pdf").write_text("content")
        renamed_path = working_dir / "transfBBVA_to_Banamex_x128.00_May2026.pdf"
        renamed_path.write_text("content")

        plan = [{
            "original": "source.pdf",
            "new_name": "transfBBVA_to_Banamex_x128.00_May2026.pdf",
            "new_path": renamed_path,
        }]

        copied, moved = archive_processed(
            plan, input_dir,
            processed_dir=processed_dir,
            dry_run=False,
        )
        assert moved == 1
        assert not (input_dir / "source.pdf").exists()
        assert (processed_dir / "source.pdf").exists()

    def test_skips_incomplete_entries(self, tmp_path):
        """Entries with new_name=None are skipped."""
        input_dir = tmp_path / "input"
        processed_dir = tmp_path / "processed"
        input_dir.mkdir()

        (input_dir / "bad.pdf").write_text("content")

        plan = [{
            "original": "bad.pdf",
            "new_name": None,
        }]

        copied, moved = archive_processed(
            plan, input_dir,
            processed_dir=processed_dir,
            dry_run=False,
        )
        assert copied == 0
        assert moved == 0
        # Source should NOT be moved
        assert (input_dir / "bad.pdf").exists()

    def test_dry_run_does_not_modify_files(self, tmp_path):
        """In dry-run mode, no files are copied or moved."""
        input_dir = tmp_path / "input"
        working_dir = tmp_path / "working"
        processed_dir = tmp_path / "processed"
        renamed_dir = tmp_path / "renamed"
        input_dir.mkdir()
        working_dir.mkdir()

        (input_dir / "source.pdf").write_text("content")
        renamed_path = working_dir / "renamed.pdf"
        renamed_path.write_text("content")

        plan = [{
            "original": "source.pdf",
            "new_name": "renamed.pdf",
            "new_path": renamed_path,
        }]

        copied, moved = archive_processed(
            plan, input_dir,
            processed_dir=processed_dir,
            renamed_dir=renamed_dir,
            dry_run=True,
        )
        # Dry run reports what would happen but doesn't touch files
        assert (input_dir / "source.pdf").exists()
        # Dirs may be created (mkdir -p) but should be empty
        assert not any(processed_dir.iterdir()) if processed_dir.exists() else True
        assert not any(renamed_dir.iterdir()) if renamed_dir.exists() else True

    def test_both_renamed_and_processed(self, tmp_path):
        """Both renamed_dir and processed_dir can be used together."""
        input_dir = tmp_path / "input"
        working_dir = tmp_path / "working"
        processed_dir = tmp_path / "processed"
        renamed_dir = tmp_path / "renamed"
        input_dir.mkdir()
        working_dir.mkdir()

        (input_dir / "source.pdf").write_text("content")
        renamed_path = working_dir / "renamed.pdf"
        renamed_path.write_text("content")

        plan = [{
            "original": "source.pdf",
            "new_name": "renamed.pdf",
            "new_path": renamed_path,
        }]

        copied, moved = archive_processed(
            plan, input_dir,
            processed_dir=processed_dir,
            renamed_dir=renamed_dir,
            dry_run=False,
        )
        assert copied == 1
        assert moved == 1
        assert (renamed_dir / "renamed.pdf").exists()
        assert (processed_dir / "source.pdf").exists()
        assert not (input_dir / "source.pdf").exists()