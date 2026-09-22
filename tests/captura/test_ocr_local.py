"""Humo del motor real con una factura sintética; no usa servicios externos."""

import io
import os

import pytest

from app.domain.captura.extraction import extract
from app.services.captura.ocr import recognize


@pytest.mark.skipif(os.environ.get("CAPTURA_TEST_OCR") != "1", reason="OCR real opcional")
def test_real_ocr_synthetic_invoice():
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(600, 700))
    pdf.setFont("Helvetica", 18)
    lines = [
        "FACTURA ELECTRONICA",
        "F001-00000123",
        "RUC: 20000000001",
        "Fecha: 18/09/2026",
        "Subtotal: S/ 100.00",
        "IGV: S/ 18.00",
        "Total: S/ 118.00",
    ]
    for index, line in enumerate(lines):
        pdf.drawString(50, 650 - index * 45, line)
    pdf.save()
    result = recognize(stream.getvalue(), "application/pdf")
    document = extract(result)
    assert document.classification.type == "FACTURA", result.text
    assert document.fields["document.issue_date"].value == "2026-09-18", result.text
    assert document.fields["amounts.total"].value == "118.00", result.text
    assert result.blocks[0].bbox
