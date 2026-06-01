"""Unit tests for pdf_sort.rename module."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from pdf_sort.extract import TransactionInfo
from pdf_sort.rename import build_filename, deduplicate, fmt_amount, fmt_month_year

MX_TZ = ZoneInfo("America/Mexico_City")


class TestFmtAmount:
    def test_small(self):
        assert fmt_amount(128.0) == "128.00"

    def test_thousands(self):
        assert fmt_amount(52713.61) == "52,713.61"

    def test_zero(self):
        assert fmt_amount(0.0) == "0.00"


class TestFmtMonthYear:
    def test_may_2026(self):
        dt = datetime(2026, 5, 10, tzinfo=MX_TZ)
        assert fmt_month_year(dt) == "May2026"

    def test_apr_2026(self):
        dt = datetime(2026, 4, 30, tzinfo=MX_TZ)
        assert fmt_month_year(dt) == "Apr2026"


class TestBuildFilename:
    def test_complete_info(self):
        info = TransactionInfo(
            date=datetime(2026, 5, 10, tzinfo=MX_TZ),
            source_bank="BBVA",
            dest_bank="Banamex",
            amount=128.0,
        )
        assert build_filename(info) == "transfBBVA_to_Banamex_x128.00_May2026.pdf"

    def test_with_suffix(self):
        info = TransactionInfo(
            date=datetime(2026, 5, 10, tzinfo=MX_TZ),
            source_bank="BBVA",
            dest_bank="Banamex",
            amount=128.0,
        )
        assert build_filename(info, suffix="2") == "transfBBVA_to_Banamex_x128.00_May2026_2.pdf"

    def test_incomplete_returns_none(self):
        info = TransactionInfo(date=None, source_bank="UNKNOWN", dest_bank="OTHER", amount=None)
        assert build_filename(info) is None

    def test_no_duplicate_pdf_extension(self):
        """LO-5: Should not produce .pdf.pdf"""
        info = TransactionInfo(
            date=datetime(2026, 4, 30, tzinfo=MX_TZ),
            source_bank="Santander",
            dest_bank="BBVA",
            amount=3000.0,
        )
        result = build_filename(info)
        assert result.endswith(".pdf")
        assert not result.endswith(".pdf.pdf")


class TestDeduplicate:
    def test_no_collisions(self):
        info1 = TransactionInfo(datetime(2026, 4, 30, tzinfo=MX_TZ), "Santander", "BBVA", 3000.0)
        info2 = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 128.0)
        plan = [
            {"original": "a.pdf", "path": "/tmp/a.pdf", "info": info1},
            {"original": "b.pdf", "path": "/tmp/b.pdf", "info": info2},
        ]
        result = deduplicate(plan)
        assert result[0]["new_name"] == "transfSantander_to_BBVA_x3,000.00_Apr2026.pdf"
        assert result[1]["new_name"] == "transfBBVA_to_Banamex_x128.00_May2026.pdf"

    def test_collision_gets_suffix(self):
        """CR-1 fix: colliding names get _2, _3, etc."""
        info1 = TransactionInfo(datetime(2026, 4, 30, tzinfo=MX_TZ), "Santander", "MercadoPago", 300.0)
        info2 = TransactionInfo(datetime(2026, 4, 30, tzinfo=MX_TZ), "Santander", "MercadoPago", 300.0)
        plan = [
            {"original": "a.pdf", "path": "/tmp/a.pdf", "info": info1},
            {"original": "b.pdf", "path": "/tmp/b.pdf", "info": info2},
        ]
        result = deduplicate(plan)
        assert result[0]["new_name"] == "transfSantander_to_MercadoPago_x300.00_Apr2026.pdf"
        assert result[1]["new_name"] == "transfSantander_to_MercadoPago_x300.00_Apr2026_2.pdf"

    def test_incomplete_skipped(self):
        """ME-6: incomplete records get new_name=None"""
        info = TransactionInfo(date=None, source_bank="UNKNOWN", dest_bank="OTHER", amount=None)
        plan = [{"original": "bad.pdf", "path": "/tmp/bad.pdf", "info": info}]
        result = deduplicate(plan)
        assert result[0]["new_name"] is None