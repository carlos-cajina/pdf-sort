# pdf-sort

Rename Mexican bank transfer PDF receipts with consistent, descriptive filenames.

Extracts the **source bank**, **destination bank**, **amount**, and **transaction date** from PDF receipts (BBVA, Banamex, Santander) and renames each file to:

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
  --execute              Actually rename files (default is dry-run)
  --input-dir DIR        Directory containing source PDFs (default: ~/Downloads)
  --output-dir DIR       Directory to copy and rename files into (default: current dir)
  --overwrite            Overwrite existing files when copying (default: True)
  -v, --verbose          Enable debug-level logging
  -h, --help             Show help message and exit
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

> Note: `--overwrite` is the default. Use `--no-overwrite` to skip files that already exist.

---

## Output Format

Filenames follow this pattern:

```
transf<SourceBank>_to_<DestinationBank>_x<Amount>_MMMYYYY.pdf
```

| Part | Description | Example |
|------|-------------|---------|
| `SourceBank` | Bank the money was sent **from** (PascalCase) | `BBVA`, `Banamex`, `Santander` |
| `DestinationBank` | Bank the money was sent **to** (PascalCase) | `Banamex`, `Santander`, `MercadoPago`, `Banorte`, `BBVA` |
| `Amount` | Transfer amount in MXN, Mexico formatting | `52,713.61`, `128.00`, `3,000.00` |
| `MMMYYYY` | Transaction month and year | `May2026`, `Apr2026` |

### Example renames

| Original filename | Renamed to |
|-------------------|-----------|
| `1778422750.pdf` | `transfBBVA_to_Banamex_x128.00_May2026.pdf` |
| `TransactionRecord_1777545114464.pdf` | `transfBanamex_to_Santander_x52,713.61_Apr2026.pdf` |
| `pagodetdcaotrosbancos-27-04-26.pdf` | `transfSantander_to_BBVA_x3,000.00_Apr2026.pdf` |

---

## Supported Banks

| Source Bank | Receipt Type | Detected By |
|-------------|-------------|-------------|
| **BBVA** | Interbank transfers | `Banco destino:` + `BBVA` markers |
| **Banamex** | Interbank transfers, credit card payments | `MiCuenta Banamex`, `Pago a tarjetas Banamex` |
| **Santander** | Transfers, credit card payments (own & other) | `Banco Santander` markers |

| Destination Bank | Detected From |
|-----------------|---------------|
| `Banamex` | CLABE/bank name in deposit account field |
| `Santander` | CLABE/bank name in deposit account field |
| `BBVA` | Credit card bank name (`BBVA Bancomer`) |
| `Banorte` | CLABE beneficiary name |
| `MercadoPago` | CLABE beneficiary name |
| `Costco` | Credit card brand name |

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

---

## Project Structure

```
pdf-sort/
├── README.md
├── CODE_REVIEW.md
├── rename_transfers.py          ← backward-compatible entry point
├── pdf_sort/
│   ├── __init__.py
│   ├── __main__.py              ← `python3 -m pdf_sort`
│   ├── extract.py               ← date, bank, amount extraction
│   ├── rename.py                ← filename building, deduplication
│   ├── io.py                    ← file copy, sanitize, rename with rollback
│   └── cli.py                   ← CLI argument parsing, orchestration
└── tests/
    ├── test_extraction.py       ← 29 tests (dates, banks, amounts)
    ├── test_rename.py           ← 10 tests (filenames, dedup)
    └── test_io.py               ← 8 tests (sanitize, copy)
```

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

```
49 passed in 0.08s
```

---

## Configuration (Advanced)

Supported banks are defined in `pdf_sort/extract.py` as the `BANK_SIGNATURES` dict. To add a new bank, add an entry:

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
