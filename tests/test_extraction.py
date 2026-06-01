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
    _clean_text,
    TransactionInfo,
)

MX_TZ = ZoneInfo("America/Mexico_City")


# ── _clean_text (Ph1-1D) ────────────────────────────────────────────────

class TestCleanText:
    def test_strips_uffff(self):
        assert _clean_text("BBV\uffff\uffffM\u00e9xico") == "BBVM\u00e9xico"

    def test_strips_ufffd(self):
        assert _clean_text("test\ufffdhere") == "testhere"

    def test_strips_null(self):
        assert _clean_text("abc\x00def") == "abcdef"

    def test_preserves_normal_text(self):
        assert _clean_text("BBVA M\u00e9xico, S.A.") == "BBVA M\u00e9xico, S.A."


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

    # ── Ph1-1B: hyphenated dates ──────────────────────────────────
    def test_hyphenated_fecha_operacion(self):
        """22-04-2026 (BBVA SPEI receipt)"""
        text = "Fecha de operación:22-04-2026"
        assert parse_date(text) == datetime(2026, 4, 22, tzinfo=MX_TZ)

    def test_hyphenated_fecha_aplicacion(self):
        text = "Fecha de aplicación:22-04-2026"
        assert parse_date(text) == datetime(2026, 4, 22, tzinfo=MX_TZ)

    def test_hyphenated_bare(self):
        """Bare DD-MM-YYYY in text"""
        text = "Some text 31-05-2026 more text"
        assert parse_date(text) == datetime(2026, 5, 31, tzinfo=MX_TZ)

    # ── Ph2-2A: AmEx date format ──────────────────────────────────
    def test_amex_fecha_multiline(self):
        text = "Fecha\n14 may, 2026"
        assert parse_date(text) == datetime(2026, 5, 14, tzinfo=MX_TZ)


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

# Ph2-2D: BBVA SPEI without "BBVA" in text (like WUBCOPF010)
_BBVA_SPEI_NO_BRAND_TEXT = """\
Operación:Transferencias a otros bancos SPEI
Fecha de operación:22-04-2026
Hora de operación:09:46 horas
Cuenta origen:ENLACE PERSONAL - 1194086203
Nombre de ordenante:CARLOS ERNESTO CAJINA MORALES
Cuenta destino:CARLOS_SANTANDER - 014320606103186784
Banco destino:Santander
Importe a pagar:$ 14,080.00 MN
"""

# Ph2-2D: BBVA own-TDC (descarga.pdf after cleaning corruption)
_BBVA_OWN_TDC_TEXT = """\
CAJINA MORALES CARLOS ERNESTO
Tarjeta de crédito
Comprobante 04 May 2026 15:34:51
CUENTA DE RETIRO  1572633671
CUENTA DESTINO  4772133048882663
IMPORTE  $10,000.00
FECHA DE OPERACIÓN  04/05/2026 3:34:48 PM
TIPO DE OPERACIÓN  TRASPASO CUENTAS PROPIAS (TDC)
FOLIO DE OPERACIÓN  20050007
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

# Ph2-2C: Santander programmed TDC payment
_SANTANDER_PROGRAMMED_TEXT = """\
Banco Santander (México), S.A.
¡Programaste el pago de una tarjeta!
Cuenta de origen CTA *8678 Supercuenta Cheques
Fecha y hora de operación 22/may/26 - 21:27:42
Número de tarjeta TDC *2663 - BBVA BANCOMER
Motivo o concepto Pago a BBVA Oro
$10,224.01
Importe Pagado:
"""

# Ph2-2B: Santander transfer to Nu Mexico
_SANTANDER_TO_NU_TEXT = """\
Banco Santander (México), S.A.
Transferencia a otros bancos - SPEI
Cuenta origen CTA *8678 Supercuenta Cheques
Fecha y hora de operación 24/abr/2026 - 17:15:29 h
Número de cuenta *2832 - Nu Mexico
$500.00
Importe total (MXN)
"""

# Ph2-2B: Santander transfer to third-party Santander
_SANTANDER_TO_SANTANDER_TEXT = """\
Banco Santander (México), S.A.
Transferencia a terceros Santander
Cuenta de origen CTA *8678 Supercuenta Cheques
Fecha de operación 14/may/2026
Cuenta *5697 - Santander
$215.00
Importe total (MXN)
"""

# Ph2-2B: Santander to null/debit card
_SANTANDER_TO_NULL_TEXT = """\
Banco Santander (México), S.A.
Transferencia enviada, en proceso de validación
Cuenta de origen CTA *8678 Supercuenta Cheques
Fecha y hora de operación 31/may/2026 - 20:41:29 h
Tarjeta de débito *4494 - null
$4,500.00
Importe total (MXN)
"""

# Ph2-2A: American Express
_AMEX_TEXT = """\
American Express - Confirm Payment
Gracias por tu Pago. Has enviado un pago para tu La Tarjeta American
Express® Aeroméxico (-22009).
Cuenta Bancaria
SANTANDER - 6784
Importe del pago en Pesos
$6,602.43
Fecha
14 may, 2026
"""


class TestIdentifyBanks:
    # ── Existing tests ─────────────────────────────────────────────
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
        assert dst == "Costco"

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

    # ── Ph2-2D: BBVA SPEI without BBVA text ────────────────────────
    def test_bbva_spei_enlace_personal_to_santander(self):
        """BBVA SPEI: detected via ENLACE PERSONAL + BANCO DESTINO"""
        src, dst = identify_banks(_BBVA_SPEI_NO_BRAND_TEXT)
        assert src == "BBVA"
        assert dst == "Santander"

    # ── Ph2-2D: BBVA own-TDC ───────────────────────────────────────
    def test_bbva_own_tdc(self):
        """BBVA own credit card payment (descarga.pdf)"""
        src, dst = identify_banks(_BBVA_OWN_TDC_TEXT)
        assert src == "BBVA"
        assert dst == "BBVA"

    # ── Ph2-2C: Santander programmed TDC ───────────────────────────
    def test_santander_programmed_tdc_to_bbva(self):
        src, dst = identify_banks(_SANTANDER_PROGRAMMED_TEXT)
        assert src == "Santander"
        assert dst == "BBVA"

    # ── Ph2-2B: Santander to Nu Mexico ─────────────────────────────
    def test_santander_to_nu_mexico(self):
        src, dst = identify_banks(_SANTANDER_TO_NU_TEXT)
        assert src == "Santander"
        assert dst == "NuMexico"

    # ── Ph2-2B: Santander to third-party Santander ─────────────────
    def test_santander_to_santander_terceros(self):
        src, dst = identify_banks(_SANTANDER_TO_SANTANDER_TEXT)
        assert src == "Santander"
        assert dst == "Santander"

    # ── Ph2-2B: Santander to null debit card ──────────────────────
    def test_santander_to_null_debit(self):
        src, dst = identify_banks(_SANTANDER_TO_NULL_TEXT)
        assert src == "Santander"
        assert dst == "OTHER"

    # ── Ph2-2A: American Express ──────────────────────────────────
    def test_amex_from_santander(self):
        src, dst = identify_banks(_AMEX_TEXT)
        assert src == "Santander"
        assert dst == "Amex"

    # ── Ph2-2D: SANTANDER in BANCO DESTINO doesn't trigger fallback ──
    def test_santander_in_banco_destino_not_source(self):
        """SANTANDER appearing only as destination bank should not trigger source=Santander"""
        text = "Banco destino:Santander\nSome other bank details"
        src, dst = identify_banks(text)
        # Without explicit source markers, should be UNKNOWN (not Santander)
        assert src == "UNKNOWN"


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
        text = "Comisión por Transferencia - envío; $5.00 + IVA"
        assert extract_amount(text) is None
        text2 = "Importe: $128.00\nComisión por Transferencia $5.00 + IVA"
        assert extract_amount(text2) == 128.00

    def test_costo_line_excluded(self):
        """CR-3: Costo lines must not be matched as the principal amount."""
        text = "Costo de la operación + IVA $0.00"
        assert extract_amount(text) is None
        text2 = "Importe total (MXN)\n$300.00\nCosto de la operación + IVA $0.00"
        assert extract_amount(text2) == 300.00

    def test_monto_pattern(self):
        text = "Monto\n$3,500.00\nMXN"
        assert extract_amount(text) == 3500.00

    # ── Ph1-1A: whole-number amounts (no decimals) ────────────────────
    def test_whole_number_importe_total_mxn(self):
        """$85 without decimals (pagodetdcpropia-14-05-26)"""
        text = "Importe total (MXN)\n$85"
        assert extract_amount(text) == 85.00

    def test_whole_number_importe_pagado(self):
        """$900 without decimals (recibobancario SAT)"""
        text = "Importe Pagado:\n$900"
        assert extract_amount(text) == 900.00

    def test_whole_number_standalone_dollar(self):
        """Bare $85 on a line"""
        text = "Some text\n$85\nMore text"
        assert extract_amount(text) == 85.00

    # ── Ph1-1C: Importe a pagar ───────────────────────────────────────
    def test_importe_a_pagar(self):
        """BBVA SPEI: Importe a pagar:$ 14,080.00 MN"""
        text = "Importe a pagar:$ 14,080.00 MN"
        assert extract_amount(text) == 14080.00

    # ── Ph2-2A: AmEx amount ──────────────────────────────────────────
    def test_importe_del_pago_en_pesos(self):
        """AmEx: Importe del pago en Pesos\n$6,602.43"""
        text = "Importe del pago en Pesos\n$6,602.43"
        assert extract_amount(text) == 6602.43

    # ── Ph1-1A + Ph2-2C: Importe Pagado with decimals ─────────────────
    def test_importe_pagado_multiline_with_decimals(self):
        text = "Importe Pagado:\n$10,224.01"
        assert extract_amount(text) == 10224.01


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

    # ── Ph2-2B: new aliases ───────────────────────────────────────
    def test_nu_mexico_alias(self):
        assert _clean_bank_name("Nu Mexico") == "NuMexico"
        assert _clean_bank_name("NU MEXICO") == "NuMexico"

    def test_american_express_alias(self):
        assert _clean_bank_name("American Express") == "Amex"


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

    # ── Ph1-1D: corrupted text cleaning ──────────────────────────────
    def test_corrupt_text_cleaning(self):
        """descarga.pdf: U+FFFF chars are stripped before processing"""
        corrupt_text = (
            "BBV\uffff\uffffM\u00e9xico, S.\uffff., "
            "Instituci\u00f3n\uffffde\uffffBanca\uffffM\u00faltiple, "
            "Grupo\uffffFinanciero\uffffBBV\uffff\uffffM\u00e9xico.\n"
            "IMPORTE \uffff $10,000.00\n"
            "CUENT\uffff\uffffDESTINO \uffff 4772133048882663\n"
            "Tarjeta\uffffde\uffffcr\u00e9dito\n"
            "TIPO\uffffDE\uffffOPER\uffffCI\u00d3N \uffff TR\uffffSP\uffffSO\uffffCUENT\uffffS\uffffPROPI\uffffS\uffff(TDC)\n"
            "FECH\uffff\uffffDE\uffffOPER\uffffCI\u00d3N \uffff 04/05/2026\uffff3:34:48\uffffPM"
        )
        info = extract_info(corrupt_text)
        assert info.source_bank == "BBVA"
        assert info.dest_bank == "BBVA"  # own TDC
        assert info.amount == 10000.00
        assert info.date is not None
        assert info.date.day == 4
        assert info.is_complete()

    # ── Ph2-2D: BBVA SPEI without BBVA text ──────────────────────────
    def test_bbva_spei_no_brand_full(self):
        info = extract_info(_BBVA_SPEI_NO_BRAND_TEXT)
        assert info.source_bank == "BBVA"
        assert info.dest_bank == "Santander"
        assert info.amount == 14080.00
        assert info.date == datetime(2026, 4, 22, tzinfo=MX_TZ)
        assert info.is_complete()

    # ── Ph2-2A: American Express ────────────────────────────────────
    def test_amex_full(self):
        info = extract_info(_AMEX_TEXT)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "Amex"
        assert info.amount == 6602.43
        assert info.date == datetime(2026, 5, 14, tzinfo=MX_TZ)
        assert info.is_complete()

    # ── Ph1-1A: whole-number amount ──────────────────────────────────
    def test_whole_number_amount_full(self):
        text = """\
Banco Santander (México), S.A.
Pago de TDC propia
Fecha de operación 14/may/2026
$85
Importe total (MXN)
"""
        info = extract_info(text)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "Santander"
        assert info.amount == 85.00
        assert info.is_complete()

    # ── Ph2-2C: programmed TDC ─────────────────────────────────────
    def test_programmed_tdc_full(self):
        info = extract_info(_SANTANDER_PROGRAMMED_TEXT)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "BBVA"
        assert info.amount == 10224.01
        assert info.is_complete()

    # ── Ph2-2B: Nu Mexico ──────────────────────────────────────────
    def test_santander_to_nu_full(self):
        info = extract_info(_SANTANDER_TO_NU_TEXT)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "NuMexico"
        assert info.amount == 500.00
        assert info.is_complete()

    # ── Ph2-2B: Santander to Santander third-party ──────────────────
    def test_santander_to_santander_terceros_full(self):
        info = extract_info(_SANTANDER_TO_SANTANDER_TEXT)
        assert info.source_bank == "Santander"
        assert info.dest_bank == "Santander"
        assert info.amount == 215.00
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


def test_santander_costo_layout_whole_number():
    """Santander with $0.00 MXN / Costo / $500 — should extract 500 (whole number)."""
    text = """\
Banco Santander (México), S.A.
Transferencia a otros bancos - SPEI
Número de cuenta *2473 - BBVA Mexico
$0.00 MXN
Costo de la operación + IVA
$500
Importe total (MXN)
"""
    info = extract_info(text)
    assert info.amount == 500.00


def test_sat_recibo_bancario():
    """SAT tax payment receipt: whole-number amount $900."""
    text = """\
Banco Santander (México), S.A.
Recibo Bancario de Pago de Contribuciones, Productos y Aprovechamientos Federales
Fecha y Hora de Pago: 14/05/2026 - 19:15 Hrs
$900
Importe Pagado:
"""
    info = extract_info(text)
    assert info.source_bank == "Santander"
    assert info.amount == 900.00
    assert info.date is not None
