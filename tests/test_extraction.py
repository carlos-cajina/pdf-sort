"""Unit tests for pdf_sort.extract module."""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from pdf_sort.extract import (
    parse_date,
    identify_banks,
    extract_amount,
    extract_info,
    _clean_bank_name,
    TransactionInfo,
)

MX_TZ = ZoneInfo("America/Mexico_City")


# ── parse_date ─────────────────────────────────────────────────────────

class TestParseDate:
    def test_dd_mon_yyyy_english(self):
        text = "30 Apr 2026 04:31:50"
        assert parse_date(text) == datetime(2026, 4, 30, tzinfo=MX_TZ)

    def test_dd_mon_yyyy_spanish(self):
        text = "10/may/2026 - 06:26:56 h"
        assert parse_date(text) == datetime(2026, 5, 10, tzinfo=MX_TZ)

    def test_fecha_operacion_santander(self):
        text = "Fecha de operación 30/abr/2026"
        assert parse_date(text) == datetime(2026, 4, 30, tzinfo=MX_TZ)

    def test_fecha_hora_operacion_santander(self):
        text = "Fecha y hora de operación 30/abr/2026 - 04:35:52 h"
        assert parse_date(text) == datetime(2026, 4, 30, tzinfo=MX_TZ)

    def test_fecha_hora_aplicacion_santander(self):
        text = "Fecha y hora de aplicación 27/abr/2026 - 06:10:22 h"
        assert parse_date(text) == datetime(2026, 4, 27, tzinfo=MX_TZ)

    def test_banamex_spanish_month(self):
        text = "30 Abr 2026"
        assert parse_date(text) == datetime(2026, 4, 30, tzinfo=MX_TZ)

    def test_fecha_aplicacion_banamex(self):
        text = "Fecha de aplicación: 10 May 2026"
        assert parse_date(text) == datetime(2026, 5, 10, tzinfo=MX_TZ)

    def test_numeric_dd_mm_yyyy(self):
        text = "Fecha de operación: 10/05/2026"
        assert parse_date(text) == datetime(2026, 5, 10, tzinfo=MX_TZ)

    def test_none_on_no_match(self):
        assert parse_date("random text without dates") is None


# ── identify_banks ──────────────────────────────────────────────────────

_BBVA_TEXT = """\
CAJINA MORALES CARLOS ERNESTO
A otros bancos - Cuenta CLABE
Comprobante 10/May/2026 08:19:07
Cuenta de retiro: 1572633671
Tipo de operación: Transferir - Otros bancos - Cuenta CLABE
Banco destino: BANAMEX
Importe: $128.00
Comisión por Transferencia - envío; (SPEI; $5.00 + IVA
Fecha de operación: 10/05/2026
BBVA México, S.A., Institución de Banca Múltiple, Grupo Financiero BBVA México.
"""

_BANAMEX_INTERBANK_TEXT = """\
Pago interbancario
CARLOS ERNESTO CAJINA MORALES 30 Abr 2026 04:31:50
Cuenta de retiro: MiCuenta Banamex **954 MXN
Cuenta de depósito: CARLOS SANTANDER-SANTANDER-CLABE-784-
Importe: $ 52,713.61
Fecha: 30 Abr 2026
"""

_BANAMEX_TDC_TEXT = """\
Comprobante de pago de tarjetas
30 Apr 2026 4:32:56 h
Pago a tarjetas Banamex
CARLOS ERNESTO CAJINA MORALES
Tarjeta de crédito
Costco Baname... **280
Importe: $3,500.00
Cuenta de retiro
MiCuenta Baname... **954
"""

_SANTANDER_TDC_OTHER_TEXT = """\
Banco Santander (México), S.A.
Pago de TDC a otros bancos
Cuenta de origen
CTA *8678 Supercuenta Cheques
Fecha de operación 30/abr/2026
Número de tarjeta TDC *2663 - BBVA Bancomer
Importe total (MXN)
$3,000.00
"""

_SANTANDER_TDC_OWN_TEXT = """\
Banco Santander (México), S.A.
Pago de TDC propia
Cuenta de origen
CTA *8678 Supercuenta Cheques
Fecha de operación 30/abr/2026
Nombre SANTANDER LIKEU
$8,139.28
Importe total (MXN)
"""

_SANTANDER_TRANSFER_TEXT = """\
Banco Santander (México), S.A.
Transferencia enviada, en proceso de validación
Cuenta de origen CTA *8678 Supercuenta Cheques
Fecha y hora de operación 30/abr/2026 - 04:35:52 h
Número de cuenta CLABE *2072 - Mercado Pago W
$207.78
Importe total (MXN)
"""


class TestIdentifyBanks:
    def test_bbva_to_banamex(self):
        src, dst = identify_banks(_BBVA_TEXT)
        assert src == "BBVA"
        assert dst == "Banamex"

    def test_banamex_interbank_to_santander(self):
        src, dst = identify_banks(_BANAMEX_INTERBANK_TEXT)
        assert src == "Banamex"
        assert dst == "Santander"

    def test_banamex_tdc_to_costco(self):
        src, dst = identify_banks(_BANAMEX_TDC_TEXT)
        assert src == "Banamex"
        assert dst == "TDCCostcoBaname"

    def test_santander_tdc_other_to_bbva(self):
        src, dst = identify_banks(_SANTANDER_TDC_OTHER_TEXT)
        assert src == "Santander"
        assert dst == "BBVA"

    def test_santander_tdc_own(self):
        src, dst = identify_banks(_SANTANDER_TDC_OWN_TEXT)
        assert src == "Santander"
        assert dst == "Santander"

    def test_santander_transfer_to_mercadopago(self):
        src, dst = identify_banks(_SANTANDER_TRANSFER_TEXT)
        assert src == "Santander"
        assert dst == "MercadoPago"

    def test_unknown_returns_unknown(self):
        src, dst = identify_banks("Random text no bank markers")
        assert src == "UNKNOWN"
        assert dst == "UNKNOWN"


# ── extract_amount ──────────────────────────────────────────────────────

class TestExtractAmount:
    def test_importe_with_dollar(self):
        text = "Importe: $128.00\nComisión por Transferencia: $5.00 + IVA"
        assert extract_amount(text) == 128.00

    def test_importe_with_commas(self):
        text = "Importe: $ 52,713.61"
        assert extract_amount(text) == 52713.61

    def test_importe_total_mxn(self):
        text = "$3,000.00\nImporte total (MXN)"
        assert extract_amount(text) == 3000.00

    def test_standalone_dollar(self):
        text = "Importe total (MXN)\n$147.45"
        assert extract_amount(text) == 147.45

    def test_commission_line_excluded(self):
        """CR-3: Comisión lines must not be matched as the principal amount."""
        # When only commission lines exist (no principal), result is None
        text = "Comisión por Transferencia - envío; $5.00 + IVA"
        assert extract_amount(text) is None
        # Principal present alongside commission → only principal matched
        text2 = "Importe: $128.00\nComisión por Transferencia $5.00 + IVA"
        assert extract_amount(text2) == 128.00

    def test_costo_line_excluded(self):
        """CR-3: Costo lines must not be matched as the principal amount."""
        # Costo line alone should be skipped
        text = "Costo de la operación + IVA $0.00"
        assert extract_amount(text) is None
        # Principal present alongside costo → only principal matched
        text2 = "Importe total (MXN)\n$300.00\nCosto de la operación + IVA $0.00"
        assert extract_amount(text2) == 300.00

    def test_monto_pattern(self):
        text = "Monto\n$3,500.00\nMXN"
        assert extract_amount(text) == 3500.00


# ── _clean_bank_name ────────────────────────────────────────────────────

class TestCleanBankName:
    def test_acronym_stays_upper(self):
        assert _clean_bank_name("BBVA") == "BBVA"
        assert _clean_bank_name("HSBC") == "HSBC"
        assert _clean_bank_name("TDC") == "TDC"

    def test_uppercase_converted_to_title(self):
        assert _clean_bank_name("BANAMEX") == "Banamex"
        assert _clean_bank_name("SANTANDER") == "Santander"

    def test_lowercase_converted_to_title(self):
        assert _clean_bank_name("bancomer") == "Bancomer"

    def test_mixed_case_preserved_strip_spaces(self):
        assert _clean_bank_name("Mercado Pago") == "MercadoPago"
        assert _clean_bank_name("Banorte") == "Banorte"

    def test_bank_aliases_resolve(self):
        assert _clean_bank_name("BBVA Mexico") == "BBVA"
        assert _clean_bank_name("BBVA MEXICO") == "BBVA"
        assert _clean_bank_name("BBVA Bancomer") == "BBVA"
        assert _clean_bank_name("Mercado Pago W") == "MercadoPago"


# ── extract_info (integration) ──────────────────────────────────────────

class TestExtractInfo:
    def test_bbva_full(self):
        info = extract_info(_BBVA_TEXT)
        assert info.source_bank == "BBVA"
        assert info.dest_bank == "Banamex"
        assert info.amount == 128.00
        assert info.date is not None
        assert info.date.year == 2026
        assert info.is_complete()

    def test_santander_transfer_full(self):
        info = extract_info(_SANTANDER_TRANSFER_TEXT)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "MercadoPago"
        assert info.amount == 207.78
        assert info.is_complete()


def test_santander_costo_layout_amount():
    """Amount is $600.00 even when preceded by a $0.00 cost placeholder."""
    text = """\
Banco Santander (México), S.A.
Transferencia enviada
Número de cuenta CLABE *2473 - BBVA Mexico
$0.00 MXN
Costo de la operación + IVA
$600.00
Importe total (MXN)
"""
    info = extract_info(text)
    assert info.amount == 600.00
    assert info.dest_bank == "BBVA"  # "BBVA Mexico" → alias resolved