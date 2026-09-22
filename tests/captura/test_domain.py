from datetime import date

import pytest

from app.domain.captura.classification import classify
from app.domain.captura.extraction import extract, money, parse_date
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
