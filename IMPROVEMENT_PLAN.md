# `pdf-sort` — Improvement Plan

**Date:** 2026-06-01
**Reviewer:** Pi
**Status:** Phase 0 in progress

---

## 1. Snapshot

| | |
|---|---|
| Modules | `extract` (511) · `rename` (69) · `io` (145) · `cli` (195) |
| Entry points | `python3 -m pdf_sort`, `rename_transfers.py` (legacy shim, **deprecated**) |
| Test ratio | ~1:1 (core:tests) |
| External deps | `pdfplumber` only; stdlib for everything else |
| Distribution | none — no `pyproject.toml` |

Solid foundation. Issues below, grouped by severity.

---

## 2. Issues Found

### Critical

- **C1.** `--overwrite` default contradicts README and defeats CR-2 fix (`cli.py:49`).
- **C2.** Bare 2-digit date pattern can match CLABE/phone fragments (`extract.py:71`).
- **C3.** Bare `$N.NN` pattern can match a balance/header line if pattern ordering breaks (`extract.py:90`).

### High

- **H1.** `identify_banks` is a 180-line nested if-else wall (`extract.py:313-450`).
- **H2.** `archive_processed` does two unrelated things — copy renames + move originals (`io.py:95`).
- **H3.** `deduplicate` mutates inputs and returns them (`rename.py:47`).
- **H4.** `rename_with_rollback` rollback errors can shadow the original exception (`io.py:71-76`).
- **H5.** No packaging — can't `pip install`, no `[project.scripts]`.
- **H6.** No CI, no coverage tooling.

### Medium

- **M1.** `_find_source_in_dir` is O(n) per call, called per file (`io.py:81`).
- **M2.** Untyped plan dicts threaded through 3 modules.
- **M3.** Hardcoded 2-digit year → 2000 (`extract.py:232`).
- **M4.** `archive_processed` creates output dirs in dry-run (`io.py:121, 134`).
- **M5.** Fuzzy BBVA match success is silent (`extract.py:345-365`).
- **M6.** `cli.main()` returns `plan` but `__main__.py` discards it.
- **M7.** No tests for `parse_args`, `main`, `setup_logging`.
- **M8.** `Path.rename` fails cross-device (`io.py:68`).
- **M9.** PII (account numbers, names) in INFO logs.
- **M10.** No pinned deps in `requirements.txt`.
- **M11.** `sanitize_filename` collides `My File.pdf` and `My_File.pdf`.

### Low

- **L1.** (skipped — non-issue)
- **L2.** `BANK_SIGNATURES` is `Final` `dict` — can't load from YAML.
- **L3.** `MONTH_MAP_ES` duplicates English `calendar.month_abbr` logic.
- **L4.** `extract_amount` O(P×L) per PDF.
- **L5.** `parse_date` returns first match — stray dates win over `Fecha de operación`.
- **L6.** Tests miss: `parse_args`, `main`, `rename_with_rollback`.
- **L7.** Silent no-op when both archival dirs are None.
- **L8.** `__version__` never surfaced (no `--version`).
- **L9.** README "Future Enhancements" lists 7 aspirational items, none tracked.

---

## 3. UI Options

| # | Option | New deps | Effort | Best for |
|---|---|---|---|---|
| **F1** | Interactive CLI (`questionary` per-file y/n/edit) | `questionary` or 0 | XS | Power user, terminal-first |
| **F2** | TUI (`textual` table) | `textual` | M | Batch review of 50+ receipts |
| **F3** | Streamlit web app (browser drag-drop) | `streamlit` | S | Non-technical, demos |
| **F4** | JSON output (`--format json`) | 0 | XS | Automation, scripting |

**Chosen:** F1 (interactive CLI) + F4 (JSON output). F2/F3 deferred.

---

## 4. Phased Plan

### Phase 0 — Correctness quick wins *(in progress)*
- [x] **C1** Fix `--overwrite` default: add `--no-overwrite` flag, default overwrite=on.
- [x] **C2** Add `\b` to numeric date patterns.
- [x] **C3** Anchor bare `$` amount pattern to line start.
- [x] **M3** 2-digit year century inference.
- [x] **M5** `logger.warning` on fuzzy BBVA match.
- [x] **H4** Preserve original exception in `rename_with_rollback`.
- [x] **M8** Replace `Path.rename` with `shutil.move`.

### Phase 1 — CLI ergonomics
- [ ] `--format {text,json}` output.
- [ ] `--version` flag.
- [ ] Exit codes: 0 / 1 / 2.
- [ ] `--limit N`.
- [ ] `--no-color` / `NO_COLOR` env.
- [ ] `--interactive` flag (F1) with `questionary` confirm-per-file.

### Phase 2 — Architecture
- [ ] **H1** Refactor `identify_banks` into per-bank dispatchers.
- [ ] **H2** Rename `archive_processed` → `archive_results` or split.
- [ ] **H3** Make `deduplicate` pure.
- [ ] **M2** TypedDict for plan items.
- [ ] **M1** Build source index dict once.
- [ ] **M4** Move `mkdir` behind `if not dry_run`.

### Phase 3 — Test coverage
- [ ] **M7** Tests for `parse_args`, `main`, `setup_logging`, `rename_with_rollback`.
- [ ] `pytest-cov` + `--cov-fail-under=90`.
- [ ] `hypothesis` property tests for `_clean_text`, `sanitize_filename`.

### Phase 4 — Packaging & CI
- [ ] **H5** `pyproject.toml` (PEP 621), pin deps, declare Python 3.9+.
- [ ] `[project.scripts] pdf-sort = "pdf_sort.cli:main"`.
- [ ] **H6** GitHub Actions: `pytest` + `ruff` + `mypy --strict` on 3.9/3.12/3.13.
- [ ] `pre-commit`: `ruff format`, `ruff check`, `mypy`.
- [ ] Mark `rename_transfers.py` as deprecated (kept for back-compat).

### Phase 5 — Robustness features
- [ ] CLABE prefix → bank code lookup (Banxico).
- [ ] OCR fallback (`pdf2image` + `pytesseract`).
- [ ] SQLite audit trail.
- [ ] Multi-transaction PDFs.
- [ ] Currency detection.
- [ ] **M9** `--redact` mode.
- [ ] **L2** `--config` for `BANK_SIGNATURES`.
- [ ] **L5** Date preference: `Fecha de operación` first.

### Phase 6 — Future UI
- [ ] **F2** Textual TUI.
- [ ] **F3** Streamlit web app.

---

## 5. Execution Order

1. Phase 0 — Day 1 *(now)*.
2. Phase 1 (F4 first) — Day 1 PM.
3. Phase 1 (F1) — Day 2.
4. Phase 2 — Day 3-4.
5. Phase 3 — Day 5.
6. Phase 4 — Day 5.
7. Phase 5 — 1-2 days each, behind feature flags.

---

## 6. Notes

- `rename_transfers.py` shim kept, marked deprecated. Remove in v3.0.
- Current branch: `feature/bank-detection-enhancements`.
