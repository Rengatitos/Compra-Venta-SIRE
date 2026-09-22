import pytest

from app.domain.captura.models import OCRBlock, OCRResult


@pytest.fixture
def ocr_factory():
    def make(*lines: str, confidence: float = 0.98) -> OCRResult:
        return OCRResult(
            blocks=[
                OCRBlock(
                    text=line,
                    confidence=confidence,
                    bbox=[[0, i * 20], [400, i * 20], [400, i * 20 + 18], [0, i * 20 + 18]],
                )
                for i, line in enumerate(lines)
            ]
        )

    return make


@pytest.fixture
def invoice(ocr_factory):
    return ocr_factory(
        "FACTURA ELECTRONICA",
        "F001-00000123",
        "RUC: 20000000001",
        "Razon social: EMPRESA SINTETICA DE PRUEBA",
        "Fecha: 18/09/2026",
        "Subtotal: S/ 144.14",
        "IGV: S/ 25.95",
        "Total: S/ 170.09",
        "Concepto: PRODUCTO DE PRUEBA",
    )
