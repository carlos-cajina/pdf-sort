"""Unit tests for pdf_sort.output module."""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pdf_sort.extract import TransactionInfo
from pdf_sort.output import (
    FileResult,
    RunSummary,
    _iso_date,
    format_json,
    format_output,
    format_text,
    result_from_plan_item,
    want_color,
)

MX_TZ = ZoneInfo("America/Mexico_City")


def _sample_info() -> TransactionInfo:
    return TransactionInfo(
        date=datetime(2026, 5, 10, tzinfo=MX_TZ),
        source_bank="BBVA",
        dest_bank="Banamex",
        amount=128.0,
    )


# ── FileResult / RunSummary ─────────────────────────────────────────────


class TestDataclasses:
    def test_file_result_fields(self):
        r = FileResult(
            original="a.pdf", status="renamed", new_name="b.pdf",
            source_bank="BBVA", dest_bank="Banamex", amount=128.0,
            date="2026-05-10", error=None,
        )
        assert r.original == "a.pdf"
        assert r.status == "renamed"

    def test_run_summary_defaults(self):
        s = RunSummary(total=5, renamed=3, skipped=1, errors=1, dry_run=False)
        assert s.copied == 0
        assert s.moved == 0


# ── result_from_plan_item ───────────────────────────────────────────────


class TestResultFromPlanItem:
    def test_complete_item(self):
        item = {
            "original": "x.pdf",
            "path": "/tmp/x.pdf",
            "info": _sample_info(),
            "new_name": "transfBBVA_to_Banamex_x128.00_May2026.pdf",
        }
        r = result_from_plan_item(item, status="renamed")
        assert r.original == "x.pdf"
        assert r.new_name == "transfBBVA_to_Banamex_x128.00_May2026.pdf"
        assert r.source_bank == "BBVA"
        assert r.dest_bank == "Banamex"
        assert r.amount == 128.0
        assert r.date == "2026-05-10"
        assert r.error is None

    def test_error_propagates(self):
        item = {"original": "y.pdf", "path": "/tmp/y.pdf", "info": _sample_info(), "new_name": None}
        r = result_from_plan_item(item, status="error", error="pdf read failed")
        assert r.status == "error"
        assert r.error == "pdf read failed"

    def test_none_date(self):
        info = TransactionInfo(date=None, source_bank="UNKNOWN", dest_bank="OTHER", amount=None)
        item = {"original": "z.pdf", "path": "/tmp/z.pdf", "info": info, "new_name": None}
        r = result_from_plan_item(item, status="skipped")
        assert r.date is None


class TestIsoDate:
    def test_aware_datetime(self):
        dt = datetime(2026, 5, 10, tzinfo=MX_TZ)
        assert _iso_date(dt) == "2026-05-10"

    def test_none(self):
        assert _iso_date(None) is None


# ── want_color ──────────────────────────────────────────────────────────


class TestWantColor:
    def test_flag_disables(self):
        assert want_color(True) is False

    def test_env_disables(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert want_color(False) is False

    def test_env_empty_value_still_disables(self, monkeypatch):
        # NO_COLOR convention: presence (any value) disables color
        monkeypatch.setenv("NO_COLOR", "")
        assert want_color(False) is False

    def test_default_enables(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert want_color(False) is True


# ── format_text ─────────────────────────────────────────────────────────


class TestFormatText:
    def _results(self) -> list[FileResult]:
        return [
            FileResult(
                original="a.pdf", status="renamed",
                new_name="transfBBVA_to_Banamex_x128.00_May2026.pdf",
                source_bank="BBVA", dest_bank="Banamex", amount=128.0,
                date="2026-05-10", error=None,
            ),
            FileResult(
                original="b.pdf", status="skipped",
                new_name=None, source_bank="UNKNOWN", dest_bank="OTHER",
                amount=None, date=None, error=None,
            ),
            FileResult(
                original="c.pdf", status="error",
                new_name=None, source_bank=None, dest_bank=None,
                amount=None, date=None, error="read failed",
            ),
        ]

    def test_dry_run_header(self):
        s = RunSummary(total=3, renamed=1, skipped=1, errors=1, dry_run=True)
        out = format_text(self._results(), s, use_color=False)
        assert "PROPOSED RENAMES" in out
        assert "DRY RUN complete" in out
        assert "[OK]" in out
        assert "[WARN]" in out
        assert "[ERR]" in out

    def test_execute_header(self):
        s = RunSummary(total=3, renamed=1, skipped=1, errors=1, dry_run=False)
        out = format_text(self._results(), s, use_color=False)
        assert "RENAMING FILES" in out
        assert "Done! 1 file(s) renamed" in out

    def test_color_markers(self):
        s = RunSummary(total=1, renamed=1, skipped=0, errors=0, dry_run=True)
        r = [FileResult(
            original="a.pdf", status="renamed", new_name="b.pdf",
            source_bank="BBVA", dest_bank="Banamex", amount=128.0,
            date="2026-05-10", error=None,
        )]
        out = format_text(r, s, use_color=True)
        assert "✓" in out
        assert "[OK]" not in out

    def test_archive_summary_shown(self):
        s = RunSummary(total=1, renamed=1, skipped=0, errors=0,
                       dry_run=False, copied=1, moved=1)
        r = [FileResult(
            original="a.pdf", status="renamed", new_name="b.pdf",
            source_bank="BBVA", dest_bank="Banamex", amount=128.0,
            date="2026-05-10", error=None,
        )]
        out = format_text(r, s, use_color=False)
        assert "1 file(s) copied to renamed dir" in out
        assert "1 file(s) moved to processed dir" in out


# ── format_json ─────────────────────────────────────────────────────────


class TestFormatJson:
    def test_valid_json(self):
        s = RunSummary(total=2, renamed=1, skipped=1, errors=0, dry_run=True)
        r = [
            FileResult(
                original="a.pdf", status="renamed", new_name="b.pdf",
                source_bank="BBVA", dest_bank="Banamex", amount=128.0,
                date="2026-05-10", error=None,
            ),
        ]
        out = format_json(r, s)
        parsed = json.loads(out)
        assert parsed["summary"]["total"] == 2
        assert parsed["summary"]["dry_run"] is True
        assert len(parsed["files"]) == 1
        assert parsed["files"][0]["original"] == "a.pdf"
        assert parsed["files"][0]["status"] == "renamed"
        assert parsed["files"][0]["date"] == "2026-05-10"

    def test_unicode_preserved(self):
        s = RunSummary(total=1, renamed=1, skipped=0, errors=0, dry_run=True)
        r = [FileResult(
            original="NuMéxico.pdf", status="renamed", new_name="x.pdf",
            source_bank="BBVA", dest_bank="NuMexico", amount=1.0,
            date="2026-05-10", error=None,
        )]
        out = format_json(r, s)
        assert "NuMéxico" in out


# ── format_output dispatch ──────────────────────────────────────────────


class TestFormatOutput:
    def test_dispatch_json(self):
        s = RunSummary(total=0, renamed=0, skipped=0, errors=0, dry_run=True)
        out = format_output("json", [], s)
        json.loads(out)  # valid JSON

    def test_dispatch_text(self):
        s = RunSummary(total=0, renamed=0, skipped=0, errors=0, dry_run=True)
        out = format_output("text", [], s)
        assert "PROPOSED RENAMES" in out
