from datetime import date

import pytest

from app.domain.captura.classification import classify
from app.domain.captura.extraction import extract, money, parse_date
from app.domain.captura.models import Classification, ExtractedDocument, ExtractedField
from app.domain.captura.period import decide_period, parse_period
from app.domain.captura.validation import fingerprint, match_score, validate
from app.services.captura.privacy import SensitiveDataMasker
from app.services.captura.review import edit_changes


@pytest.mark.parametrize(
    "ocr,confidence,metadata,target,period,document,status,validation",
    [
        ("2026-09-18", 0.98, None, None, "202609", "2026-09-18", "DATE_EXTRACTED", "MATCH"),
        ("2026-09-28", 0.98, "2026-10-02", None, "202609", "2026-09-28", "DATE_EXTRACTED", "MATCH"),
        ("2026-09-18", 0.98, None, "202609", "202609", "2026-09-18", "DATE_EXTRACTED", "MATCH"),
        ("2026-10-03", 0.98, None, "202609", "202609", "2026-10-03", "DATE_CONFLICT", "MISMATCH"),
        (
            "2026-09-18",
            0.98,
            "2026-10-02",
            "202609",
            "202609",
            "2026-09-18",
            "DATE_EXTRACTED",
            "MATCH",
        ),
        (None, 0, "2026-09-18", None, "202609", None, "DATE_FROM_METADATA", "UNVERIFIED"),
        (None, 0, None, "202609", "202609", None, "DATE_NOT_FOUND", "UNVERIFIED"),
        (
            "2026-09-18",
            0.4,
            "2026-09-17",
            "202609",
            "202609",
            None,
            "DATE_FROM_BATCH_PERIOD",
            "UNVERIFIED",
        ),
        (None, 0, None, None, None, None, "DATE_NOT_FOUND", "UNVERIFIED"),
    ],
)
def test_period_rules(ocr, confidence, metadata, target, period, document, status, validation):
    result = decide_period(
        date.fromisoformat(ocr) if ocr else None,
        confidence,
        date.fromisoformat(metadata) if metadata else None,
        target,
    )
    assert result.accounting_period == period
    assert result.document_date == (date.fromisoformat(document) if document else None)
    assert result.date_status == status
    assert result.period_validation == validation
    if validation == "MISMATCH":
        assert "DATE_PERIOD_MISMATCH" in result.issues


def test_period_input_and_january_boundary():
    assert parse_period("SEPTIEMBRE 2026") == "202609"
    assert parse_period("2", date(2026, 1, 3)) == "202512"
    assert parse_period("202613") is None
    assert parse_date("31/02/2026") is None


@pytest.mark.parametrize(
    "text,kind",
    [
        ("FACTURA ELECTRONICA", "FACTURA"),
        ("BOLETA DE VENTA", "BOLETA"),
        ("NOTA DE CREDITO\nFACTURA ELECTRONICA F001-123", "NOTA_CREDITO"),
        ("NOTA DE DEBITO\nFACTURA F001-123", "NOTA_DEBITO"),
        ("RECIBO POR HONORARIOS", "HONORARIOS"),
        ("YAPEASTE", "YAPE_TRANSFER"),
        ("YAPE\nPAGO DE SERVICIO", "YAPE_SERVICE_PAYMENT"),
        ("PLIN", "PLIN_TRANSFER"),
        ("APROBADA\nVISA\nTERMINAL", "POS_VOUCHER"),
        ("RECIBO DE AGUA", "SERVICIO_PUBLICO"),
        ("un documento que no reconocemos", "UNKNOWN"),
    ],
)
def test_weighted_classification(text, kind):
    assert classify(text).type == kind


def test_invoice_fields_and_evidence(invoice):
    result = extract(invoice)
    assert result.fields["amounts.total"].value == "170.09"
    assert result.fields["document.issue_date"].value == "2026-09-18"
    assert result.fields["document.series"].value == "F001"
    assert result.fields["document.number"].value == "00000123"
    assert result.fields["issuer.name"].value == "EMPRESA SINTETICA DE PRUEBA"
    assert result.fields["amounts.total"].page == 1
    assert result.fields["amounts.total"].bbox
    assert fingerprint(result) == fingerprint(extract(invoice))
    assert {"rule": "TOTAL_ARITHMETIC", "status": "PASS"} in validate(result)


@pytest.mark.parametrize(
    "line,value,status",
    [
        ("Placa:", None, "PRESENT_EMPTY"),
        ("Placa: ABC-123", "ABC-123", "EXTRACTED"),
        ("Placa: ilegible", None, "ILLEGIBLE"),
        ("GASOHOL PREMIUM", None, "NOT_PRESENT"),
    ],
)
def test_fuel_plate(ocr_factory, line, value, status):
    document = extract(ocr_factory("BOLETA DE VENTA", "Concepto: GASOHOL PREMIUM", line))
    assert document.fields["vehicle.plate"].value == value
    assert document.fields["vehicle.plate"].status == status


def test_yape_service_does_not_invent_tax_data(ocr_factory):
    result = extract(ocr_factory("YAPE", "PAGO DE SERVICIO", "S/ 27.50", "Operacion: 000123"))
    assert result.fields["amounts.total"].value == "27.50"
    assert result.fields["payment.operation_number"].value == "000123"
    assert result.fields["amounts.igv"].value is None
    assert result.fields["vehicle.plate"].status == "NOT_APPLICABLE"


def test_ambiguous_fields_are_not_chosen_arbitrarily(ocr_factory):
    result = extract(ocr_factory("Total: 10.00", "Total: 20.00"))
    assert result.fields["amounts.total"].value is None
    assert result.fields["amounts.total"].status == "ILLEGIBLE"


def test_due_date_is_not_issue_date(ocr_factory):
    result = extract(ocr_factory("Fecha de vencimiento: 20/10/2026"))
    assert result.fields["document.issue_date"].value is None


def test_card_data_masked():
    masked = SensitiveDataMasker.cards("TARJETA: 4111 1111 1111 1234")
    assert "4111" not in masked
    assert masked.endswith("1234")
    assert money("S/ 1,234.50") == "1234.50"
    assert money("1.234,50") == "1234.50"


def test_matching_requires_real_values_and_currency():
    left = {
        "family": "TAX",
        "document_date": "2026-09-18",
        "extracted": {
            "fields": {
                "amounts.total": {"value": "170.09"},
                "document.currency": {"value": "PEN"},
                "issuer.name": {"value": "COMERCIO SINTETICO"},
            }
        },
    }
    right = {
        "family": "PAYMENT",
        "document_date": "2026-09-18",
        "extracted": {
            "fields": {
                "amounts.total": {"value": "170.09"},
                "document.currency": {"value": "PEN"},
                "payment.merchant": {"value": "COMERCIO SINTETICO"},
            }
        },
    }
    assert match_score(left, right) == 90
    right["extracted"]["fields"]["document.currency"]["value"] = "USD"
    assert match_score(left, right) == 0
    assert match_score({"family": "TAX"}, {"family": "PAYMENT"}) == 0


def test_manual_change_revalidates_arithmetic(invoice):
    previous = {"extracted": extract(invoice).model_dump(), "accounting_period": "202609"}
    result = edit_changes(previous, {"fields": {"amounts.total": "999.00"}})
    assert result["status"] == "NEEDS_REVIEW"
    assert {"rule": "TOTAL_ARITHMETIC", "status": "FAIL"} in result["validations"]


def test_fixing_document_date_clears_old_period_mismatch(invoice):
    previous = {
        "extracted": extract(invoice).model_dump(),
        "accounting_period": "202609",
        "issues": ["DATE_PERIOD_MISMATCH"],
        "period_validation": "MISMATCH",
    }
    result = edit_changes(previous, {"fields": {"document.issue_date": "2026-09-18"}})
    assert "DATE_PERIOD_MISMATCH" not in result["issues"]
    assert result["period_validation"] == "MATCH"


def test_layout_joins_label_and_value_only_on_same_line():
    from app.domain.captura.models import OCRBlock, OCRResult

    ocr = OCRResult(
        blocks=[
            OCRBlock(text="Total:", confidence=0.99, bbox=[[0, 0], [50, 0], [50, 20], [0, 20]]),
            OCRBlock(
                text="S/ 118.00", confidence=0.98, bbox=[[60, 0], [180, 0], [180, 20], [60, 20]]
            ),
            OCRBlock(text="Placa:", confidence=0.99, bbox=[[0, 40], [50, 40], [50, 60], [0, 60]]),
        ]
    )
    result = extract(ocr)
    assert result.fields["amounts.total"].value == "118.00"
    assert result.fields["vehicle.plate"].status == "PRESENT_EMPTY"


def test_extracts_items_only_under_explicit_header(ocr_factory):
    document = extract(
        ocr_factory(
            "FACTURA ELECTRONICA",
            "CANT DESCRIPCION PRECIO TOTAL",
            "2 UND PRODUCTO SINTETICO 50.00 100.00",
            "Total: S/ 100.00",
        )
    )
    assert len(document.items) == 1
    assert document.items[0]["quantity"].value == "2"
    assert {"rule": "ITEM_ARITHMETIC:0", "status": "PASS"} in validate(document)


@pytest.mark.parametrize("value", ["12,34,56", "1,23.45", "1.23.45", "1.234,5,6", "NaN", "Infinity"])
def test_money_rejects_malformed_numbers(value):
    assert money(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [("S/ 1,234.50", "1234.50"), ("1.234,50", "1234.50"), ("usd 12.5", "12.50"),
     ("EUR 1234,50", "1234.50"), ("0", "0.00"), ("1,234,567.89", "1234567.89")],
)
def test_money_preserves_supported_grouping(value, expected):
    assert money(value) == expected


@pytest.mark.parametrize("value", ["18/09/026", "20260-09-18", "18/09/2026 y 19/09/2026"])
def test_date_does_not_guess_malformed_or_conflicting_year(value):
    assert parse_date(value) is None


def test_period_canonicalizes_user_input_and_peruvian_month_name():
    assert parse_period("setiembre 2026") == "202609"
    result = decide_period(date(2026, 9, 18), 0.99, None, "2026-09")
    assert result.accounting_period == "202609"
    assert result.period_validation == "MATCH"


def test_classification_handles_ocr_whitespace():
    assert classify("NOTA  DE\nCRÉDITO\nFactura electrónica F001-12").type == "NOTA_CREDITO"


@pytest.mark.parametrize(
    "line,currency", [("Moneda: soles", "PEN"), ("Moneda: Dólares americanos", "USD"),
                      ("Moneda: EUR", "EUR")],
)
def test_explicit_currency_is_normalized(ocr_factory, line, currency):
    result = extract(ocr_factory(line))
    assert result.fields["document.currency"].value == currency


def test_currency_conflict_is_not_chosen_arbitrarily(ocr_factory):
    result = extract(ocr_factory("Subtotal: S/ 100.00", "Total: USD 118.00"))
    assert result.fields["document.currency"].value is None
    assert result.fields["document.currency"].status == "ILLEGIBLE"


def test_explicit_currency_is_not_overwritten_by_exchange_reference(ocr_factory):
    result = extract(ocr_factory("Moneda: soles", "Tipo de cambio: USD 3.80"))
    assert result.fields["document.currency"].value == "PEN"


@pytest.mark.parametrize("label,status", [("Total:", "PRESENT_EMPTY"), ("Total: ilegible", "ILLEGIBLE")])
def test_payment_fallback_preserves_explicit_field_status(ocr_factory, label, status):
    result = extract(ocr_factory("YAPEASTE", label, "S/ 100.00"))
    assert result.fields["amounts.total"].status == status
    assert result.fields["amounts.total"].value is None


def test_payment_standalone_totals_conflict(ocr_factory):
    result = extract(ocr_factory("YAPEASTE", "S/ 100.00", "S/ 200.00"))
    assert result.fields["amounts.total"].status == "ILLEGIBLE"
    assert result.fields["amounts.total"].value is None


def test_payment_malformed_standalone_total_is_illegible(ocr_factory):
    result = extract(ocr_factory("YAPEASTE", "S/ 12,34,56"))
    assert result.fields["amounts.total"].status == "ILLEGIBLE"


def test_note_reference_on_following_line_is_not_the_note_number(ocr_factory):
    result = extract(ocr_factory("NOTA DE CREDITO", "FC01-00000123", "DOCUMENTO AFECTADO",
                                 "FACTURA ELECTRONICA", "F001-00000999"))
    assert result.fields["document.series"].value == "FC01"
    assert result.fields["document.number"].value == "00000123"
    assert result.fields["references.series"].value == "F001"
    assert result.fields["references.number"].value == "00000999"
    assert result.fields["references.document_type"].value == "01"


def test_note_does_not_use_only_visible_invoice_as_own_number(ocr_factory):
    result = extract(ocr_factory("NOTA DE CREDITO", "Factura afectada F001-123"))
    assert result.fields["document.number"].status == "NOT_PRESENT"
    assert result.fields["references.number"].value == "123"


def test_conflicting_document_numbers_require_review(ocr_factory):
    result = extract(ocr_factory("FACTURA ELECTRONICA", "F001-12", "F001-13"))
    assert result.fields["document.number"].status == "ILLEGIBLE"
    assert result.fields["document.number"].value is None


@pytest.mark.parametrize("label", ["Fecha de vencimiento:", "Fecha de traslado:", "Periodo facturado:"])
def test_standalone_date_after_other_date_label_is_not_issue_date(ocr_factory, label):
    result = extract(ocr_factory("FACTURA ELECTRONICA", label, "18/09/2026"))
    assert result.fields["document.issue_date"].value is None


def test_reference_document_date_is_not_issue_date(ocr_factory):
    result = extract(ocr_factory("NOTA DE CREDITO", "Fecha documento afectado: 18/09/2026"))
    assert result.fields["document.issue_date"].value is None


def test_item_quantity_and_literal_description_are_preserved(ocr_factory):
    result = extract(ocr_factory("CANT DESCRIPCION PRECIO TOTAL",
                                 "0,125 KG Café orgánico 80.00 10.00"))
    item = result.items[0]
    assert item["quantity"].value == "0.125"
    assert item["description"].value == "Café orgánico"
    assert item["description"].raw_text == "0,125 KG Café orgánico 80.00 10.00"
    assert {"rule": "ITEM_ARITHMETIC:0", "status": "PASS"} in validate(result)


def test_raw_value_preserves_combining_unicode_accents(ocr_factory):
    result = extract(ocr_factory("Razo\u0301n social: Café\u0301"))
    assert result.fields["issuer.name"].value == "Café\u0301"


def test_item_grouped_price_and_invalid_amount(ocr_factory):
    result = extract(ocr_factory("CANT DESCRIPCION PRECIO TOTAL",
                                 "2 UND Servicio sintético 1,250.00 2,500.00",
                                 "1 UND Otro servicio 1,23.00 23.00"))
    assert result.items[0]["unit_price"].value == "1250.00"
    assert result.items[1]["unit_price"].value is None
    assert result.items[1]["unit_price"].status == "ILLEGIBLE"


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "un monto", "1e1000000"])
def test_invalid_amounts_do_not_crash_validation(invoice, bad_value):
    document = extract(invoice)
    document.fields["amounts.total"].value = bad_value
    assert {"rule": "POSITIVE_TOTAL", "status": "FAIL"} in validate(document)


def test_validation_accepts_partial_item_without_key_errors(invoice):
    document = extract(invoice)
    document.items = [{"description": ExtractedField(value="Producto ilegible")}]
    assert {"rule": "ITEM_ARITHMETIC:0", "status": "WARNING"} in validate(document)


def test_arithmetic_accounts_for_explicit_discounts_and_other_taxes(ocr_factory):
    document = extract(ocr_factory("Subtotal: 100.00", "IGV: 18.00", "Otros tributos: 5.00",
                                   "Descuento: 10.00", "Total: 113.00"))
    assert {"rule": "TOTAL_ARITHMETIC", "status": "PASS"} in validate(document)
    document.items = [{key: ExtractedField(value=value) for key, value in {
        "quantity": "2", "unit_price": "50.00", "discount": "5.00", "total": "95.00",
    }.items()}]
    assert {"rule": "ITEM_ARITHMETIC:0", "status": "PASS"} in validate(document)


def test_fingerprint_without_extracted_fields_is_absent():
    assert fingerprint(ExtractedDocument(classification=Classification(family="TAX"))) is None


def match_document(family, amount="100.00", when="2026-09-18", hour="12:00"):
    return {
        "family": family, "document_date": when,
        "extracted": {"fields": {key: {"value": value} for key, value in {
            "amounts.total": amount, "document.currency": "PEN",
            "document.issue_time": hour, "issuer.name": "Comercio sintético",
        }.items()}},
    }


def test_matching_only_pairs_tax_document_and_payment():
    assert match_score(match_document("OTHER"), match_document("PAYMENT")) == 0


def test_matching_uses_nearby_times_on_same_document_date():
    assert match_score(match_document("TAX"), match_document("PAYMENT", hour="12:04")) == 100
    assert match_score(match_document("TAX"), match_document("PAYMENT", hour="12:06")) == 90
    assert match_score(match_document("TAX"), match_document("PAYMENT", when="2026-09-19")) == 70


@pytest.mark.parametrize("amount", [None, "NaN", "Infinity", "1e1000000", "0", "-100"])
def test_matching_invalid_or_nonpositive_amount_does_not_suggest(amount):
    assert match_score(match_document("TAX", amount), match_document("PAYMENT", amount)) < 85


def test_matching_does_not_count_invalid_dates_or_times():
    left = match_document("TAX", when="no se ve", hour="no se ve")
    right = match_document("PAYMENT", when="no se ve", hour="no se ve")
    assert match_score(left, right) == 70
