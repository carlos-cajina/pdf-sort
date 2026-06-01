"""Backward-compatible entry point — delegates to the pdf_sort package."""

from pdf_sort.cli import main

if __name__ == "__main__":
    main()