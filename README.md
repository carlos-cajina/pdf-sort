# pdf-sort

Rename Mexican bank transfer PDF receipts with consistent, descriptive filenames.

Extracts the **source bank**, **destination bank**, **amount**, and **transaction date** from PDF receipts (BBVA, Banamex, Santander, American Express) and renames each file to:

```
transf<SourceBank>_to_<DestinationBank>_x<Amount>_MMMYYYY.pdf
```

**Example:**
```
1778422750.pdf  →  transfBBVA_to_Banamex_x128.00_May2026.pdf
```

---

## Requirements

- **Python 3.9+** (uses `zoneinfo` for timezone support)
- **pdfplumber** (PDF text extraction)
- **pytest** (optional — for running tests)

```bash
pip install pdfplumber pytest
```

---

## Quick Start

```bash
# 1. Copy PDFs from ~/Downloads and show what would happen (dry run)
python3 -m pdf_sort

# 2. Actually rename the files
python3 -m pdf_sort --execute --overwrite
```

---

## Usage

```
usage: python3 -m pdf_sort [options]

Rename Mexican bank-transfer PDF receipts with consistent filenames.

options:
  --version              Show program version and exit
  --execute              Actually rename files (default is dry-run)
  --input-dir DIR        Directory containing source PDFs (default: ~/Downloads)
  --output-dir DIR       Directory to copy and rename files into (default: current dir)
  --overwrite            Overwrite existing files when copying (default: True)
  --no-overwrite         Skip files that already exist in output dir
  --processed-dir DIR    Move successfully processed source PDFs into this directory
  --renamed-dir DIR      Copy renamed PDFs into this directory
  --limit N              Process at most N files (default: all)
  --format {text,json}   Output format: text (default) or JSON
  --interactive          Prompt for confirmation before each rename (execute mode only)
  --no-color             Strip unicode status markers; use ASCII labels
  -v, --verbose          Enable debug-level logging
  -h, --help             Show this help message and exit
```

### Examples

**Dry run with a custom folder:**
```bash
python3 -m pdf_sort --input-dir /path/to/receipts
```

**Execute renames into a specific output directory:**
```bash
python3 -m pdf_sort --execute \
  --input-dir ~/Downloads \
  --output-dir ./sorted-receipts
```

**Verbose mode (debug logging):**
```bash
python3 -m pdf_sort --execute --verbose
```

**Skip overwriting existing files in the output directory:**
```bash
python3 -m pdf_sort --execute --no-overwrite
```

**Two-stage archival workflow (move originals, copy renames):**
```bash
python3 -m pdf_sort --execute \
  --input-dir ~/Downloads \
  --output-dir /tmp/pdf_sort_work \
  --processed-dir ~/Downloads/processed \
  --renamed-dir ~/Downloads/renamed
```

**Machine-readable JSON output:**
```bash
python3 -m pdf_sort --execute --format json
```

**Process only the first 10 PDFs, interactive confirmation:**
```bash
python3 -m pdf_sort --execute --interactive --limit 10
```

**Non-TTY / pipe-friendly output (no unicode/colors):**
```bash
python3 -m pdf_sort --execute --no-color | tee log.txt
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All files processed successfully (renamed or skipped due to incomplete data) |
| `1` | At least one file was skipped (incomplete extraction) or an error occurred |

---

## Output Format

Filenames follow this pattern:

```
transf<SourceBank>_to_<DestinationBank>_x<Amount>_MMMYYYY.pdf
```

| Part | Description | Example |
|------|-------------|---------|
| `SourceBank` | Bank the money was sent **from** (PascalCase) | `BBVA`, `Banamex`, `Santander`, `Amex` |
| `DestinationBank` | Bank the money was sent **to** (PascalCase) | `Banamex`, `Santander`, `MercadoPago`, `Banorte`, `BBVA`, `Costco`, `NuMexico`, `OTHER` |
| `Amount` | Transfer amount in MXN, Mexico formatting | `52,713.61`, `128.00`, `3,000.00`, `85.00` |
| `MMMYYYY` | Transaction month and year | `May2026`, `Apr2026` |

### Example renames

| Original filename | Renamed to |
|-------------------|-----------|
| `1778422750.pdf` | `transfBBVA_to_Banamex_x128.00_May2026.pdf` |
| `TransactionRecord_1777545114464.pdf` | `transfBanamex_to_Santander_x52,713.61_Apr2026.pdf` |
| `pagodetdcaotrosbancos-27-04-26.pdf` | `transfSantander_to_BBVA_x3,000.00_Apr2026.pdf` |
| `confirmacion_de_compra_telcel.pdf` | `transfSantander_to_Costco_x5,000.00_Jul2026.pdf` |
| `1785324240.pdf` | `transfAmex_to_Banamex_x20,812.68_Aug2026.pdf` |

---

## Supported Banks

| Source Bank | Receipt Type | Detected By |
|-------------|-------------|-------------|
| **BBVA** | Interbank transfers, SPEI, own-TDC, debit card | `Banco destino:` + `BBVA` markers, `ENLACE PERSONAL`, fuzzy markers |
| **Banamex** | Interbank transfers, credit card payments | `MiCuenta Banamex`, `Pago a tarjetas Banamex`, `PAGO INTERBANCARIO` |
| **Santander** | Transfers, credit card payments (own & other), programmed TDC | `Banco Santander` markers, contact info, CLABE |
| **Amex** | American Express payments via Santander | `CONFIRM PAYMENT` + `AMERICAN EXPRESS` |

| Destination Bank | Detected From |
|-----------------|---------------|
| `Banamex` | CLABE/bank name in deposit account field |
| `Santander` | CLABE/bank name in deposit account field |
| `BBVA` | Credit card bank name (`BBVA Bancomer`) |
| `Banorte` | CLABE beneficiary name |
| `MercadoPago` | CLABE beneficiary name |
| `Costco` | Credit card brand name |
| `NuMexico` | CLABE beneficiary name |
| `OTHER` | Fallback when destination cannot be identified |

---

## How It Works

1. **Copy** — PDFs are copied from the source directory to the output directory (unsafe characters in filenames are sanitized).
2. **Extract** — Each PDF is parsed with `pdfplumber`. The text is analyzed to find:
   - Transaction date (converted to Mexico City timezone)
   - Source and destination bank names
   - Transfer amount in MXN (commission/fee lines are excluded)
3. **Build filenames** — A target filename is generated for each receipt using the extracted data.
4. **Deduplicate** — If two receipts produce the same filename, a numeric suffix (`_2`, `_3`) is added.
5. **Rename** — In dry-run mode, proposed renames are displayed. With `--execute`, files are renamed (with automatic rollback on failure).
6. **Archive (optional)** — With `--processed-dir`, original source PDFs are moved there. With `--renamed-dir`, renamed copies are placed there.

---

## Project Structure

```
pdf-sort/
├── README.md
├── CODE_REVIEW.md
├── CHANGELOG.md
├── IMPROVEMENT_PLAN.md
├── rename_transfers.py          ← deprecated backward-compatible entry point
├── pdf_sort/
│   ├── __init__.py              ← package version
│   ├── __main__.py              ← `python3 -m pdf_sort`
│   ├── cli.py                   ← CLI argument parsing, orchestration
│   ├── extract/                 ← PDF text extraction package
│   │   ├── __init__.py
│   │   ├── models.py            ← TransactionInfo dataclass, text utilities
│   │   ├── patterns.py          ← compiled regexes, bank signatures
│   │   ├── parsers.py           ← per-bank detection, date/amount parsers
│   │   └── orchestrator.py      ← identify_banks dispatcher, extract_info
│   ├── rename.py                ← filename building, deduplication
│   ├── io.py                    ← file copy, sanitize, rename with rollback, archival
│   ├── output.py                ← text/JSON formatters, FileResult, RunSummary
│   ├── interactive.py           ← per-file confirmation prompts
│   └── types.py                 ← PlanItem TypedDict
└── tests/
    ├── test_extraction.py       ← 67 tests (dates, banks, amounts)
    ├── test_rename.py           ← 10 tests (filenames, dedup)
    ├── test_io.py               ← 16 tests (sanitize, copy, archive)
    ├── test_output.py           ← 45 tests (formatters, color, dataclasses)
    ├── test_cli.py              ← 33 tests (args, main, interactive)
    └── test_architecture.py     ← architectural property tests
```

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

```
171 passed in 0.18s
```

---

## Configuration (Advanced)

Supported banks are defined in `pdf_sort/extract/patterns.py` as the `BANK_SIGNATURES` dict. To add a new bank, add an entry:

```python
BANK_SIGNATURES: dict[str, dict[str, list[str]]] = {
    # ... existing banks ...
    "MyNewBank": {
        "source_markers": ["MY BANK S.A.", "BANCO MI NUEVO BANCO"],
        # detection logic uses these strings to identify the bank
    },
}
```

---

## Future Enhancements

The following improvements are planned or suggested for future versions:

1. **CLABE-based bank lookup** — Use the first 3 digits of the CLABE account number to look up the destination bank via Banxico's bank code registry, providing more reliable detection than keyword matching.

2. **Configuration file** — Load `BANK_SIGNATURES` and other settings from a YAML/JSON config file so users can add new bank formats without editing code.

3. **OCR support** — Add `pdf2image` + `pytesseract` integration to handle scanned or image-based PDF receipts that `pdfplumber` cannot read.

4. **Audit trail** — Write extraction results (original name, extracted fields, target name, timestamp) to a JSON or SQLite file for historical tracking and cross-run deduplication.

5. **Multi-transaction PDFs** — Support bank statements that contain multiple transfers per file by extracting all transactions and generating one output file per transfer.

6. **Currency detection** — Automatically detect non-MXN amounts and convert or label them appropriately (e.g., USD receipts).

7. **Batch from stdin/pipeline** — Accept a list of file paths from stdin or a CSV manifest for processing files scattered across multiple directories.