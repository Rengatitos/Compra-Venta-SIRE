"""La BAJA original se conserva para revisión y no entra al reporte asociado."""

import json
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from app.domain.comprobante import Libro
from app.schemas.comprobante import ComprobanteResponse
from app.services.comprobante_service import serializar
from app.services.glosa import ESTADO_CON_GLOSA, ESTADO_SIN_GLOSA, OBSERVACION_BAJA_SUNAT
from app.services.plantilla_excel import excel_plantilla
from app.services.revision_comprobantes import anulado, de_baja, incompleto


@pytest.mark.parametrize("extra", [
    {"estado_comprobante": "2"},
    {"descripcion_estado_comprobante": " baja "},
    {"raw_sire": {"codEstadoComprobante": 2}},
    {"raw_sire": {"desEstadoComprobante": "BAJA"}},
    {"raw_sire": json.dumps({"codEstadoComprobante": "2", "desEstadoComprobante": "BAJA"})},
])
@pytest.mark.parametrize("glosa", [None, "Glosa conservada"])
def test_baja_en_respuesta_y_observacion_sin_modificar_original(extra, glosa):
    documento = {
        "origen": "sire", "libro": "ventas", "tipo_cp": "01",
        "serie": "F001", "numero": "1194", "serie_numero": "F001-1194",
        "documento_contraparte": "20519330874", "razon_social": "CULTIMARINE S.A.C",
        "moneda": "USD", "tipo_cambio": 0, "total": 0, "extra": extra,
    }
    if glosa is not None:
        documento["glosa"] = glosa
    original = deepcopy(documento)

    respuesta = ComprobanteResponse(**serializar(documento)).model_dump()

    assert respuesta["de_baja_sunat"] is True
    assert respuesta["observacion"] == OBSERVACION_BAJA_SUNAT
    assert respuesta["glosa"] == (glosa or "")
    assert respuesta["estado_glosa"] == (ESTADO_CON_GLOSA if glosa else ESTADO_SIN_GLOSA)
    assert respuesta["tipo_cambio"] == 0
    assert respuesta["total"] == 0
    assert de_baja(respuesta) and anulado(respuesta)
    assert documento == original


@pytest.mark.parametrize("extra", [
    {},
    {"estado_comprobante": "1", "descripcion_estado_comprobante": "ACTIVO"},
    {"raw_sire": {"codEstadoComprobante": "1", "desEstadoComprobante": "ACTIVO"}},
    {"raw_sire": {"codEstadoProceso": "02", "codEstadoEnvio": "2"}},
    {"raw_sire": {"desEstadoComprobante": "No es BAJA"}},
    {"raw_sire": "inválido"},
    {"raw_sire": "[]"},
    {"raw_sire": None},
])
def test_importes_y_tc_en_cero_no_significan_baja(extra):
    documento = {"origen": "sire", "moneda": "USD", "tipo_cambio": 0, "total": 0,
                 "extra": extra}
    respuesta = serializar(documento)
    assert respuesta["de_baja_sunat"] is False
    assert respuesta["observacion"] == ""
    assert not anulado(respuesta)


@pytest.mark.parametrize("origen", [None, "externo", "contasis"])
def test_no_aplica_estado_sunat_a_otros_origenes(origen):
    documento = {"origen": origen, "de_baja_sunat": True,
                 "extra": {"estado_comprobante": "2"}}
    assert not de_baja(documento)


def test_baja_no_se_confunde_con_datos_de_contraparte_incompletos():
    assert not incompleto({"origen": "sire", "glosa_consultada": True,
                           "extra": {"estado_comprobante": "2"}})


@pytest.mark.parametrize("libro", list(Libro))
def test_excel_individual_reserva_baja_para_revision_sin_convertirla(libro):
    baja = serializar({"origen": "sire", "libro": libro.value,
                      "serie_numero": "F001-1194", "moneda": "USD", "tipo_cambio": 0,
                      "total": 118, "base_imponible": 100, "igv": 18,
                      "extra": {"estado_comprobante": "2"}})
    activo = serializar({"origen": "sire", "libro": libro.value,
                        "serie_numero": "F001-1200", "moneda": "PEN", "total": 60})

    wb = load_workbook(excel_plantilla([baja, activo], libro))

    columna_total = "S" if libro == Libro.COMPRAS else "P"
    assert wb.worksheets[0][f"{columna_total}4"].value == 60
    assert wb.worksheets[0][f"{columna_total}5"].value == (
        f"=SUM({columna_total}4:{columna_total}4)"
    )
    assert wb["Anulados"]["A2"].value == "F001-1194"
    assert wb["Anulados"]["E2"].value == "BAJA"
