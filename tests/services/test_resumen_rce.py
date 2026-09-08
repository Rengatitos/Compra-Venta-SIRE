from app.services.sunat import resumen_rce


def test_normaliza_resumen_sin_llamarlo_total_pen():
    resultado = resumen_rce.normalizar_resumen(
        {
            "totales": {
                "cntDocumentos": 61,
                "mtoBIGravadoDG": 32892.48,
                "mtoIgvIpmDG": 5904.34,
                "mtoValorAdqNG": 2282.56,
                "mtoOtrosTribCargos": 1.15,
                "mtoTotalCP": 41080.52,
            }
        }
    )
    assert resultado["cantidad"] == 61
    assert resultado["total_original"] == "41080.52"
    assert "total_pen" not in resultado


def test_conciliacion_advierte_cantidad_distinta():
    resumen = {"cantidad": 2, "total_original": "100.00"}
    comprobante = {
        "serie": "F001", "numero": "1", "moneda": "PEN", "total": 100,
    }
    resultado = resumen_rce.conciliar(resumen, [comprobante])
    assert resultado["cantidad_coincide"] is False
    assert resultado["advertencias"]


def test_control_de_inconsistencias_no_reemplaza_cantidad_de_propuesta():
    control = resumen_rce.normalizar_control(
        {
            "numRuc": "20610202251",
            "perPeriodoTributario": "202608",
            "cantidad": {"total": 64, "porcentajeSinValidaciones": 100.0},
            "monto": {"total": 41240.520},
        }
    )
    assert control["cantidad"] == 64
    assert control["total_original"] == "41240.52"

    resumen = {"cantidad": 61, "total_original": "41080.52"}
    documentos = [
        {"serie": "F001", "numero": str(i), "moneda": "PEN", "total": 1}
        for i in range(61)
    ]
    conciliacion = resumen_rce.conciliar(resumen, documentos, control)
    assert conciliacion["cantidad_coincide"] is True
    assert conciliacion["control_global_sire"]["cantidad"] == 64
    assert any("informativo" in aviso for aviso in conciliacion["advertencias"])
