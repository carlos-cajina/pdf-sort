"""Compiled regex patterns and configuration tables for extraction.

This module is pure data: no logic, no side effects.  Importing it should
not do any work beyond compiling regexes.
"""

from __future__ import annotations

import re
from typing import Final
from zoneinfo import ZoneInfo

MX_TZ: Final = ZoneInfo("America/Mexico_City")

MONTH_MAP_ES: Final[dict[str, int]] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

_STRIP_CORRUPT_RE: Final = re.compile(r"[\uffff\ufffd\x00]")


_DATE_DMY_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"(\d{1,2})/([A-Za-z]{3,4})/(\d{4})"), "%b"),
    (re.compile(r"(\d{1,2})/([A-Za-z]{3,4})/(\d{2})"), "%y"),
    (re.compile(r"Fecha de operación\s+(\d{1,2})/([A-Za-z]{3,4})/(\d{4})"), "%b"),
    (re.compile(r"Fecha y hora de operación\s+(\d{1,2})/([A-Za-z]{3,4})/(\d{4})"), "%b"),
    (re.compile(r"Fecha y hora de operación\s+(\d{1,2})/([A-Za-z]{3,4})/(\d{2})"), "%y"),
    (re.compile(r"Fecha y hora de aplicación\s+(\d{1,2})/([A-Za-z]{3,4})/(\d{4})"), "%b"),
    (re.compile(r"(\d{1,2})\s+(Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Sept|Oct|Nov|Dic)\s+(\d{4})", re.IGNORECASE), "%b"),
    (re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
    (re.compile(r"Fecha de aplicación:\s*(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})"), "%b"),
    (re.compile(r"Fecha\s*\n(\d{1,2})\s+([A-Za-z]{3,4}),\s*(\d{4})"), "%b"),
    (re.compile(r"Fecha\s+(\d{1,2})\s+([A-Za-z]{3,4}),?\s*(\d{4})"), "%b"),
]

_DATE_NUMERIC_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"Fecha de operación:\s*(\d{2})/(\d{2})/(\d{4})\b"),
    re.compile(r"Fecha de operación:\s*(\d{2})-(\d{2})-(\d{4})\b"),
    re.compile(r"Fecha de aplicación:\s*(\d{2})-(\d{2})-(\d{4})\b"),
    re.compile(r"Fecha:\s*(\d{2})/(\d{2})/(\d{4})\b"),
    re.compile(r"\b(\d{2})/(\d{2})/(\d{4})"),
    re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b"),
]

_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"Importe del pago en\s*\$?\s*([\d,]+\.\d{2})", re.IGNORECASE),
    re.compile(r"Importe\s+\$?\s*([\d,]+\.\d{2})", re.IGNORECASE),
    re.compile(r"Importe a pagar:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe Pagado:\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe del pago en Pesos\s*\n\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe total \(MXN\)\s*\$?\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Importe Pagado:\s*\$?\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Importe:\s*\$?\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Monto\s*\$?\s*([\d,]+\.\d{2})"),
    re.compile(r"^\s*\$\s*([\d,]+\.\d{2})"),
    re.compile(r"^\s*\$\s*([\d,]+)(?:\s|$)"),
]

_MULTILINE_AMOUNT_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"\$\s*([\d,]+\.\d{2})\s*\nImporte total"),
    re.compile(r"Importe total \(MXN\)\s*\n\$\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe total \(MXN\)\s*\n\$\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Monto\s*\n\$\s*([\d,]+\.\d{2})"),
    re.compile(r"Importe Pagado:\s*\n\$\s*([\d,]+)(?:\s|$)"),
    re.compile(r"Importe Pagado:\s*\n\$\s*([\d,]+\.\d{2})"),
]

_BBVA_DEST_RE: Final = re.compile(r"Banco destino:\s*(\S+)", re.IGNORECASE)
_BANAMEX_DEP_RE: Final = re.compile(r"Cuenta de depósito:\s*(.+?)(?:\n|$)")
_BANAMEX_CARD_RE: Final = re.compile(r"Tarjeta de crédito\s*\n?([^\n]+)")
_SANTANDER_TDC_RE: Final = re.compile(r"TDC\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_CLABE_RE: Final = re.compile(r"Número de cuenta\s+CLABE\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_CONTACT_ACCT_RE: Final = re.compile(r"Número de cuenta\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_CUENTA_RE: Final = re.compile(r"Cuenta\s+\*\d+\s*-\s*([^\n]+)")
_SANTANDER_DEBITO_RE: Final = re.compile(r"Tarjeta de débito\s+\*\d+\s*-\s*([^\n]+)")
_TRAILING_LETTER_RE: Final = re.compile(r"\s+[A-Z]$")

BANK_SIGNATURES: Final[dict[str, dict[str, list[str]]]] = {
    "BBVA": {
        "source_markers": ["BBVA", "BANCO DESTINO:"],
        "alt_markers": [
            ("BANCO DESTINO:", "ENLACE PERSONAL"),
            ("BANCO DESTINO:", "TRANSFERENCIAS A OTROS BANCOS SPEI"),
        ],
        "own_tdc_markers": [
            ("BBVA", "CUENTA DESTINO", "TARJETA DE CRÉDITO"),
            ("BBVA", "TIPO DE OPERACIÓN", "TRASPASO CUENTAS PROPIAS"),
        ],
        "debit_card_markers": [
            ("TARJETA DE DÉBITO", "CUENTA DESTINO"),
        ],
        "fuzzy_markers": [
            ("BBV", "CUENT", "DESTINO", "TARJET", "CRÉDITO"),
            ("BBV", "TIPO", "OPER", "TRSPSO", "CUENTS", "PROPIS"),
        ],
        "destination_re": _BBVA_DEST_RE,
    },
    "Banamex": {
        "source_markers": [
            "MI CUENTA BANAMEX",
            "MICUENTA BANAME",
            "CUENTAS BANAMEX",
            "PAGO A TARJETAS BANAMEX",
            "COMPROBANTE DE PAGO DE TARJETAS",
        ],
        "interbank_marker": "PAGO INTERBANCARIO",
    },
    "Santander": {
        "source_markers": ["BANCO SANTANDER"],
        "tdc_other": "PAGO DE TDC A OTROS BANCOS",
        "tdc_own": "PAGO DE TDC PROPIA",
        "transfer": "TRANSFERENCIA ENVIADA",
        "programmed_tdc": "PROGRAMASTE EL PAGO DE UNA TARJETA",
    },
    "Amex": {
        "source_markers": ["AMERICAN EXPRESS", "CONFIRM PAYMENT"],
        "source_bank_indicator": "SANTANDER",
    },
}

ACRONYMS: Final[set[str]] = {"BBVA", "HSBC", "CIH", "SPEI", "TDC"}

BANK_ALIASES: Final[dict[str, str]] = {
    "BBVA MEXICO": "BBVA",
    "BBVA MEX": "BBVA",
    "BBVA BANCOMER": "BBVA",
    "BANAMEX": "Banamex",
    "SANTANDER": "Santander",
    "BANORTE": "Banorte",
    "HSBC": "HSBC",
    "MERCADO PAGO": "MercadoPago",
    "MERCADO PAGO W": "MercadoPago",
    "TDC COSTCO BANAME": "Costco",
    "NU MEXICO": "NuMexico",
    "NU": "NuMexico",
    "AMERICAN EXPRESS": "Amex",
}
