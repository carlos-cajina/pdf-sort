"""Unit tests for pdf_sort.interactive and pdf_sort.cli."""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from pdf_sort import cli as cli_module
from pdf_sort.cli import main, parse_args
from pdf_sort.extract import TransactionInfo
from pdf_sort.interactive import filter_plan_interactive

MX_TZ = ZoneInfo("America/Mexico_City")


# ── parse_args ──────────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        with patch.object(sys, "argv", ["pdf-sort"]):
            args = parse_args([])
        assert args.execute is False
        assert args.fmt == "text"
        assert args.interactive is False
        assert args.no_color is False
        assert args.limit is None
        assert args.overwrite is True

    def test_execute(self):
        with patch.object(sys, "argv", ["pdf-sort", "--execute"]):
            args = parse_args(["--execute"])
        assert args.execute is True

    def test_format_json(self):
        with patch.object(sys, "argv", ["pdf-sort", "--format", "json"]):
            args = parse_args(["--format", "json"])
        assert args.fmt == "json"

    def test_limit(self):
        with patch.object(sys, "argv", ["pdf-sort", "--limit", "5"]):
            args = parse_args(["--limit", "5"])
        assert args.limit == 5

    def test_interactive(self):
        with patch.object(sys, "argv", ["pdf-sort", "--interactive"]):
            args = parse_args(["--interactive"])
        assert args.interactive is True

    def test_no_color(self):
        with patch.object(sys, "argv", ["pdf-sort", "--no-color"]):
            args = parse_args(["--no-color"])
        assert args.no_color is True

    def test_no_overwrite(self):
        with patch.object(sys, "argv", ["pdf-sort", "--no-overwrite"]):
            args = parse_args(["--no-overwrite"])
        assert args.overwrite is False

    def test_overwrite_explicit(self):
        with patch.object(sys, "argv", ["pdf-sort", "--overwrite"]):
            args = parse_args(["--overwrite"])
        assert args.overwrite is True

    def test_verbose(self):
        with patch.object(sys, "argv", ["pdf-sort", "-v"]):
            args = parse_args(["-v"])
        assert args.verbose is True


# ── Version flag ────────────────────────────────────────────────────────


class TestVersionFlag:
    def test_version_prints_and_exits(self, capsys):
        from pdf_sort import __version__
        with pytest.raises(SystemExit) as exc_info:
            with patch.object(sys, "argv", ["pdf-sort", "--version"]):
                parse_args(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert __version__ in captured.out


# ── filter_plan_interactive ─────────────────────────────────────────────


def _info(amount: float = 100.0) -> TransactionInfo:
    return TransactionInfo(
        date=datetime(2026, 5, 10, tzinfo=MX_TZ),
        source_bank="BBVA",
        dest_bank="Banamex",
        amount=amount,
    )


_MISSING = object()


def _plan_item(name: str, new_name=_MISSING) -> dict:
    actual = f"renamed_{name}" if new_name is _MISSING else new_name
    return {
        "original": name,
        "path": Path(f"/tmp/{name}"),
        "info": _info(),
        "new_name": actual,
    }


class TestFilterPlanInteractive:
    def test_yes_passes_through(self):
        plan = [_plan_item("a.pdf"), _plan_item("b.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: "y")
        assert len(result) == 2

    def test_no_skips_item(self):
        plan = [_plan_item("a.pdf"), _plan_item("b.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: "n")
        assert len(result) == 0

    def test_all_approves_remaining(self):
        answers = iter(["n", "a"])
        plan = [_plan_item("a.pdf"), _plan_item("b.pdf"), _plan_item("c.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: next(answers))
        assert [r["original"] for r in result] == ["b.pdf", "c.pdf"]

    def test_none_rejects_remaining(self):
        answers = iter(["y", "none"])
        plan = [_plan_item("a.pdf"), _plan_item("b.pdf"), _plan_item("c.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: next(answers))
        assert [r["original"] for r in result] == ["a.pdf"]

    def test_default_yes(self):
        plan = [_plan_item("a.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: "")
        assert len(result) == 1

    def test_incomplete_items_dropped(self):
        plan = [_plan_item("a.pdf", new_name=None)]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: "y")
        assert result == []

    def test_unknown_answer_skips(self):
        plan = [_plan_item("a.pdf")]
        result = filter_plan_interactive(plan, prompt_fn=lambda *a, **k: "garbage")
        assert result == []


# ── main() end-to-end ──────────────────────────────────────────────────


class TestMainDryRun:
    """Dry-run with no real PDFs (uses an empty tmp dir)."""

    def test_no_pdfs_exits_zero(self, tmp_path, capsys):
        rc = main([
            "--input-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
            "--format", "json",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"]["total"] == 0
        assert parsed["summary"]["dry_run"] is True

    def test_no_pdfs_text_exits_zero(self, tmp_path, capsys):
        rc = main([
            "--input-dir", str(tmp_path),
            "--output-dir", str(tmp_path / "out"),
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PROPOSED RENAMES" in out

    def test_missing_input_dir_does_not_crash(self, tmp_path, capsys):
        rc = main([
            "--input-dir", str(tmp_path / "does-not-exist"),
            "--output-dir", str(tmp_path / "out"),
            "--format", "json",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"]["total"] == 0


class TestMainExitCodes:
    """Exit code = 0 if no skips, 1 if any skipped."""

    @staticmethod
    def _patched_main(tmp_path, items: list[TransactionInfo]) -> int:
        """Run main with fake PDFs (pdfplumber + extract_info mocked)."""
        from contextlib import contextmanager
        from pdf_sort import cli as cli_mod
        import pdfplumber

        class _FakePage:
            def extract_text(self_inner): return ""
        class _FakePDF:
            pages = [_FakePage()]
        @contextmanager
        def _fake_open(_path):
            yield _FakePDF()

        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        for i, _ in enumerate(items):
            (input_dir / f"file{i}.pdf").write_text("placeholder")

        iter_items = iter(items)
        with patch.object(pdfplumber, "open", _fake_open), \
             patch.object(cli_mod, "extract_info", side_effect=lambda _: next(iter_items)):
            return main([
                "--input-dir", str(input_dir),
                "--output-dir", str(output_dir),
                "--format", "json",
                "--no-color",
            ])

    def test_full_success_exit_0(self, tmp_path, capsys):
        items = [
            TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0),
            TransactionInfo(datetime(2026, 5, 11, tzinfo=MX_TZ), "Santander", "BBVA", 200.0),
        ]
        rc = self._patched_main(tmp_path, items)
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"]["renamed"] == 2
        assert parsed["summary"]["skipped"] == 0

    def test_partial_skip_exit_1(self, tmp_path, capsys):
        items = [
            TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0),
            TransactionInfo(date=None, source_bank="UNKNOWN", dest_bank="OTHER", amount=None),
        ]
        rc = self._patched_main(tmp_path, items)
        assert rc == 1
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"]["renamed"] == 1
        assert parsed["summary"]["skipped"] == 1


class TestMainExecuteMode:
    @staticmethod
    def _run_execute(tmp_path, info: TransactionInfo, extra_args: list[str] | None = None) -> int:
        from contextlib import contextmanager
        from pdf_sort import cli as cli_mod
        import pdfplumber

        class _FakePage:
            def extract_text(self_inner): return ""
        class _FakePDF:
            pages = [_FakePage()]
        @contextmanager
        def _fake_open(_path):
            yield _FakePDF()

        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        (input_dir / "src.pdf").write_text("placeholder")

        with patch.object(pdfplumber, "open", _fake_open), \
             patch.object(cli_mod, "extract_info", return_value=info):
            return main([
                "--execute",
                "--input-dir", str(input_dir),
                "--output-dir", str(output_dir),
                "--format", "json",
                *(extra_args or []),
            ])

    def test_execute_renames_files(self, tmp_path, capsys):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        rc = self._run_execute(tmp_path, info)
        assert rc == 0
        assert (tmp_path / "out" / "transfBBVA_to_Banamex_x100.00_May2026.pdf").exists()

    def test_limit_caps_files(self, tmp_path, capsys):
        from contextlib import contextmanager
        from pdf_sort import cli as cli_mod
        import pdfplumber

        class _FakePage:
            def extract_text(self_inner): return ""
        class _FakePDF:
            pages = [_FakePage()]
        @contextmanager
        def _fake_open(_path):
            yield _FakePDF()

        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        for i in range(5):
            (input_dir / f"file{i}.pdf").write_text("placeholder")

        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        with patch.object(pdfplumber, "open", _fake_open), \
             patch.object(cli_mod, "extract_info", return_value=info):
            rc = main([
                "--input-dir", str(input_dir),
                "--output-dir", str(output_dir),
                "--format", "json",
                "--limit", "2",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["summary"]["total"] == 2

    def test_archive_dirs(self, tmp_path, capsys):
        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        rc = self._run_execute(
            tmp_path, info,
            extra_args=[
                "--processed-dir", str(tmp_path / "processed"),
                "--renamed-dir", str(tmp_path / "renamed"),
            ],
        )
        assert rc == 0
        assert (tmp_path / "processed" / "src.pdf").exists()
        assert (tmp_path / "renamed" / "transfBBVA_to_Banamex_x100.00_May2026.pdf").exists()


class TestMainInteractive:
    def test_interactive_filters_plan(self, tmp_path, capsys, monkeypatch):
        from contextlib import contextmanager
        from pdf_sort import cli as cli_mod
        import pdfplumber

        class _FakePage:
            def extract_text(self_inner): return ""
        class _FakePDF:
            pages = [_FakePage()]
        @contextmanager
        def _fake_open(_path):
            yield _FakePDF()

        input_dir = tmp_path / "in"
        output_dir = tmp_path / "out"
        input_dir.mkdir()
        output_dir.mkdir()
        for i in range(3):
            (input_dir / f"file{i}.pdf").write_text("placeholder")

        info = TransactionInfo(datetime(2026, 5, 10, tzinfo=MX_TZ), "BBVA", "Banamex", 100.0)
        with patch.object(pdfplumber, "open", _fake_open), \
             patch.object(cli_mod, "extract_info", return_value=info):
            # First prompt: "n" (skip first), then "a" (approve rest)
            answers = iter(["n", "a", "a"])
            monkeypatch.setattr("builtins.input", lambda *_: next(answers))
            rc = main([
                "--execute",
                "--input-dir", str(input_dir),
                "--output-dir", str(output_dir),
                "--format", "json",
                "--interactive",
            ])
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        # Only 2 of 3 should be renamed
        assert parsed["summary"]["renamed"] == 2
