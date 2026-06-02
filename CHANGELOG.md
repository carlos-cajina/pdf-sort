# Changelog

All notable changes to pdf-sort are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `--version` flag prints the package version.
- `--format {text,json}` flag for machine-readable output.
- `--limit N` flag to process at most N files.
- `--interactive` flag prompts for confirmation per file in execute mode
  (y/n/all/none; stdlib-only, no new dependencies).
- `--no-color` flag strips unicode status markers and uses ASCII labels
  for non-TTY / pipe-friendly output.
- `pdf_sort.output` module: `FileResult`, `RunSummary` dataclasses,
  `format_text` / `format_json` / `format_output` formatters,
  `want_color` helper.
- `pdf_sort.interactive` module: `filter_plan_interactive` per-file
  confirmation; injectable `prompt_fn` for tests.
- `main()` returns an integer exit code (0 = full success,
  1 = any file skipped or errored) and is propagated through
  `__main__.py` via `sys.exit`.
- `io.copy_pdfs` accepts a `limit` parameter and raises `FileNotFoundError`
  when the input directory does not exist.
- 45 new tests in `tests/test_output.py` and `tests/test_cli.py`
  (138 total, up from 93).

### Fixed
- CLI: added `--no-overwrite` flag so users can opt out of overwriting
  existing files in the output directory (previously the only option
  was to overwrite).
- `extract.py`: numeric date patterns now use `\b` word boundaries
  so dates inside longer numbers or words are not matched.
- `extract.py`: bare `$` amount pattern is now line-anchored to avoid
  matching the dollar sign in unrelated contexts; new `Importe\s+\$?`
  variant covers receipts that print the amount label without a
  dollar sign.
- `extract.py`: 2-digit years are now inferred with proper century
  disambiguation (years < 70 → 20xx, ≥ 70 → 19xx).
- `extract.py`: fuzzy BBVA matches now log a `warning` instead of
  silently misclassifying.
- `io.py`: `copy_pdfs` rollback path now logs and continues on
  individual failures instead of aborting the whole batch.
- `io.py`: file move replaced `os.rename` with `shutil.move` so
  moves across filesystems work.
- `tests/test_extraction.py`: corrupt-date fixture text now has a
  space between the date and the time so the new boundary tests
  are realistic.

### Documentation
- `IMPROVEMENT_PLAN.md` at repo root: full code review with
  severity-ranked findings, UI options, and 6-phase improvement plan.

[Unreleased]: https://github.com/carlos-cajina/pdf-sort/compare/eca4b21...HEAD
