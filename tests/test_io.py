"""Unit tests for pdf_sort.io module."""

import pytest
import tempfile
from pathlib import Path

from pdf_sort.io import sanitize_filename, copy_pdfs


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