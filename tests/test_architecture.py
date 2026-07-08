"""Unit tests for the Phase 2 architecture refactor."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from pdf_sort.extract.parsers import (
    PARSERS,
    _parse_amex,
    _parse_bbva,
    _parse_banamex,
    _parse_santander,
    _parse_generic,
    parse_date,
)
from pdf_sort.io import (
    _build_source_index,
    archive_renamed,
    move_processed,
)
from pdf_sort.rename import deduplicate
from pdf_sort.extract import TransactionInfo
from pdf_sort.types import PlanItem

MX_TZ = ZoneInfo("America/Mexico_City")


# ── PlanItem TypedDict (M2) ────────────────────────────────────────────────

class TestPlanItem:
    def test_minimal_item(self):
        item: PlanItem = {"original": "a.pdf", "path": Path("/tmp/a.pdf"), "info": None}
        assert item["original"] == "a.pdf"
        assert item["path"] == Path("/tmp/a.pdf")

    def test_full_item(self):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        item: PlanItem = {
            "original": "a.pdf",
            "path": Path("/tmp/a.pdf"),
            "info": info,
            "new_name": "transfBBVA_to_Banamex_x100.00_May2026.pdf",
            "old_path": Path("/tmp/a.pdf"),
            "new_path": Path("/out/transfBBVA_to_Banamex_x100.00_May2026.pdf"),
        }
        assert item["new_name"] is not None
        assert item["new_path"].name == "transfBBVA_to_Banamex_x100.00_May2026.pdf"

    def test_partial_after_extract(self):
        """After _extract_entries, only original/path/info are set."""
        info = TransactionInfo(None, "UNKNOWN", "OTHER", None)
        item: PlanItem = {"original": "x.pdf", "path": Path("/t/x.pdf"), "info": info}
        assert "new_name" not in item
        assert "new_path" not in item


# ── Per-bank parsers (H1) ──────────────────────────────────────────────────

class TestPerBankParsers:
    def test_dispatch_order(self):
        """PARSERS list is ordered: Amex, BBVA, Banamex, Santander, generic."""
        assert PARSERS[0] is _parse_amex
        assert PARSERS[1] is _parse_bbva
        assert PARSERS[2] is _parse_banamex
        assert PARSERS[3] is _parse_santander
        assert PARSERS[4] is _parse_generic

    def test_amex_parser_returns_none_for_non_amex(self):
        assert _parse_amex("Random text", "RANDOM TEXT") is None

    def test_bbva_parser_returns_none_for_santander_text(self):
        text = "BANCO SANTANDER\nPAGO DE TDC A OTROS BANCOS"
        assert _parse_bbva(text, text.upper()) is None

    def test_banamex_parser_returns_none_for_bbva_text(self):
        text = "BBVA\nBanco destino: Banamex"
        assert _parse_banamex(text, text.upper()) is None

    def test_santander_parser_returns_none_for_bbva_text(self):
        text = "BBVA\nBanco destino: Nu Mexico"
        assert _parse_santander(text, text.upper()) is None

    def test_generic_parser_returns_none_for_unknown(self):
        assert _parse_generic("Random text", "RANDOM TEXT") is None

    def test_parsers_have_consistent_signature(self):
        """Each parser takes (text, text_upper) and returns tuple or None."""
        for parser in PARSERS:
            result = parser("test", "TEST")
            assert result is None or (
                isinstance(result, tuple) and len(result) == 2
            )


# ── Deduplicate purity (H3) ────────────────────────────────────────────────

class TestDeduplicatePurity:
    def test_does_not_mutate_input_items(self):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        original: PlanItem = {"original": "a.pdf", "path": Path("/tmp/a.pdf"), "info": info}
        plan = [original]
        deduplicate(plan)
        assert "new_name" not in original, "input item was mutated"

    def test_does_not_mutate_input_list(self):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        plan: list[PlanItem] = [
            {"original": "a.pdf", "path": Path("/tmp/a.pdf"), "info": info},
        ]
        result = deduplicate(plan)
        assert result is not plan, "input list reference returned"
        assert len(plan) == 1, "input list was modified"
        assert "new_name" not in plan[0]

    def test_returns_new_list_of_new_dicts(self):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        plan: list[PlanItem] = [
            {"original": "a.pdf", "path": Path("/tmp/a.pdf"), "info": info},
        ]
        result = deduplicate(plan)
        assert result[0] is not plan[0], "item reference returned, not a copy"

    def test_collisions_still_handled(self):
        """Purity doesn't break the core feature."""
        info = TransactionInfo(datetime(2026, 4, 30, tzinfo=MX_TZ), "Santander", "MercadoPago", 300.0)
        plan: list[PlanItem] = [
            {"original": "a.pdf", "path": Path("/tmp/a.pdf"), "info": info},
            {"original": "b.pdf", "path": Path("/tmp/b.pdf"), "info": info},
        ]
        result = deduplicate(plan)
        assert result[0]["new_name"] == "transfSantander_to_MercadoPago_x300.00_Apr2026.pdf"
        assert result[1]["new_name"] == "transfSantander_to_MercadoPago_x300.00_Apr2026_2.pdf"


# ── Split archive + M1 + M4 ───────────────────────────────────────────────

class TestBuildSourceIndex:
    def test_index_contains_all_pdfs(self, tmp_path):
        (tmp_path / "a.pdf").write_text("x")
        (tmp_path / "b.pdf").write_text("y")
        (tmp_path / "note.txt").write_text("z")
        index = _build_source_index(tmp_path)
        assert "a.pdf" in index
        assert "b.pdf" in index
        assert "note.txt" not in index

    def test_index_includes_sanitized_names(self, tmp_path):
        (tmp_path / "My File.pdf").write_text("x")
        index = _build_source_index(tmp_path)
        assert "My File.pdf" in index
        assert "My_File.pdf" in index

    def test_index_empty_dir(self, tmp_path):
        assert _build_source_index(tmp_path) == {}


class TestArchiveRenamed:
    def test_dry_run_does_not_create_dir(self, tmp_path, caplog):
        plan: list[PlanItem] = [{
            "original": "src.pdf",
            "new_name": "renamed.pdf",
            "new_path": tmp_path / "renamed.pdf",
        }]
        renamed_dir = tmp_path / "renamed"
        with caplog.at_level(logging.INFO):
            count = archive_renamed(plan, renamed_dir, dry_run=True)
        assert count == 1
        assert not renamed_dir.exists(), "dry-run must not mkdir (M4)"

    def test_execute_creates_dir_and_copies(self, tmp_path):
        (tmp_path / "renamed.pdf").write_text("content")
        plan: list[PlanItem] = [{
            "original": "src.pdf",
            "new_name": "renamed.pdf",
            "new_path": tmp_path / "renamed.pdf",
        }]
        renamed_dir = tmp_path / "out" / "renamed"
        count = archive_renamed(plan, renamed_dir, dry_run=False)
        assert count == 1
        assert renamed_dir.exists()
        assert (renamed_dir / "renamed.pdf").exists()

    def test_skips_items_without_new_path(self, tmp_path):
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": "x.pdf"}]
        count = archive_renamed(plan, tmp_path / "out", dry_run=False)
        assert count == 0

    def test_skips_incomplete_items(self, tmp_path):
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": None}]
        count = archive_renamed(plan, tmp_path / "out", dry_run=False)
        assert count == 0


class TestMoveProcessed:
    def test_dry_run_does_not_create_dir(self, tmp_path, caplog):
        (tmp_path / "src.pdf").write_text("x")
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": "renamed.pdf"}]
        processed_dir = tmp_path / "processed"
        with caplog.at_level(logging.INFO):
            count = move_processed(plan, tmp_path, processed_dir, dry_run=True)
        assert count == 1
        assert not processed_dir.exists(), "dry-run must not mkdir (M4)"
        assert (tmp_path / "src.pdf").exists(), "source must remain in dry-run"

    def test_execute_moves_file(self, tmp_path):
        (tmp_path / "src.pdf").write_text("x")
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": "renamed.pdf"}]
        processed_dir = tmp_path / "processed"
        count = move_processed(plan, tmp_path, processed_dir, dry_run=False)
        assert count == 1
        assert not (tmp_path / "src.pdf").exists()
        assert (processed_dir / "src.pdf").exists()

    def test_finds_sanitized_source(self, tmp_path):
        """M1: source index lets us find a file whose name needs sanitizing."""
        (tmp_path / "My File.pdf").write_text("x")
        plan: list[PlanItem] = [{"original": "My_File.pdf", "new_name": "renamed.pdf"}]
        processed_dir = tmp_path / "processed"
        count = move_processed(plan, tmp_path, processed_dir, dry_run=False)
        assert count == 1
        assert (processed_dir / "My File.pdf").exists()

    def test_skips_incomplete_items(self, tmp_path):
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": None}]
        count = move_processed(plan, tmp_path, tmp_path / "p", dry_run=False)
        assert count == 0

    def test_missing_input_dir_returns_zero(self, tmp_path):
        plan: list[PlanItem] = [{"original": "src.pdf", "new_name": "r.pdf"}]
        missing = tmp_path / "nonexistent"
        count = move_processed(plan, missing, tmp_path / "p", dry_run=False)
        assert count == 0

    def test_source_not_found_is_skipped(self, tmp_path, caplog):
        plan: list[PlanItem] = [{"original": "missing.pdf", "new_name": "r.pdf"}]
        with caplog.at_level(logging.DEBUG):
            count = move_processed(plan, tmp_path, tmp_path / "p", dry_run=True)
        assert count == 0


# ── Source index built once (M1 sanity) ────────────────────────────────────

class TestMoveProcessedSingleIndex:
    def test_processes_many_files_with_single_iteration(self, tmp_path):
        """Even with many plan items, the input dir is only scanned once."""
        for i in range(10):
            (tmp_path / f"file_{i}.pdf").write_text("x")
        plan: list[PlanItem] = [
            {"original": f"file_{i}.pdf", "new_name": f"renamed_{i}.pdf"} for i in range(10)
        ]
        processed_dir = tmp_path / "p"
        with patch(
            "pdf_sort.io._build_source_index",
            wraps=_build_source_index,
        ) as mock_idx:
            count = move_processed(plan, tmp_path, processed_dir, dry_run=False)
        assert count == 10
        assert mock_idx.call_count == 1, "source index must be built once, not per file"
