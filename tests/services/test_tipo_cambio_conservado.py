"""Recuperación del TC original sin alterar importes ni registros guardados."""

import json
from copy import deepcopy
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128
from openpyxl import load_workbook

from app.domain.comprobante import Libro
from app.services.comprobante_service import serializar
from app.services.plantilla_excel import ErrorTipoCambio, excel_plantilla


def documento(tc=None, crudo=None, libro="compras"):
    return {
        "origen": "sire", "libro": libro, "tipo_cp": "01",
        "serie": "E001", "numero": "143", "serie_numero": "E001-143",
        "documento_contraparte": "20123456789", "moneda": "USD",
        "tipo_cambio": tc, "total": Decimal128(Decimal("4413.20")),
        "base_imponible_dgng": Decimal128(Decimal("3740.00")),
        "igv_dgng": Decimal128(Decimal("673.20")),
        "extra": {"raw_sire": crudo},
    }


@pytest.mark.parametrize("libro", ["compras", "ventas"])
@pytest.mark.parametrize("guardado", [None, 0, -1])
@pytest.mark.parametrize("como_json", [False, True])
def test_recupera_tc_anidado_y_conserva_importes_y_documento(libro, guardado, como_json):
    crudo = {
        "codMoneda": "USD", "codTipoCDP": "01", "numSerieCDP": "E001",
        "numCDP": "000143", "tipoCambio": {"mtoTipoCambio": "3.740"},
    }
    fila = documento(guardado, json.dumps(crudo) if como_json else crudo, libro)
    original = deepcopy(fila)

    salida = serializar(fila)

    assert salida["tipo_cambio"] == 3.74
    assert salida["total"] == 4413.2
    assert salida["base_imponible_dgng"] == 3740
    assert salida["igv_dgng"] == 673.2
    assert fila == original


def test_tc_guardado_valido_tiene_prioridad_sobre_el_crudo():
    fila = documento(Decimal128(Decimal("3.777")), {"tipoCambio": {"mtoTipoCambio": 3.74}})
    assert serializar(fila)["tipo_cambio"] == 3.777


@pytest.mark.parametrize("invalido", [None, "", 0, "0.0", -1, "sin dato", True, "NaN", "Infinity"])
def test_busca_alias_positivo_si_el_primero_no_es_valido(invalido):
    fila = documento(crudo={"tipoCambio": {"mtoTipoCambio": invalido, "valTipoCambio": "3.740"}})
    assert serializar(fila)["tipo_cambio"] == 3.74


@pytest.mark.parametrize(
    "crudo",
    [None, "{invalid", "[]", [], {"tipoCambio": {"mtoCambioMonedaDolares": 3.74}},
     {"tipoCambio": {"mtoTipoCambio": "NaN"}}, {"tipoCambio": {"mtoTipoCambio": "Infinity"}}],
)
def test_falta_tc_real_sigue_bloqueando_exportacion(crudo):
    salida = serializar(documento(crudo=crudo))
    assert salida["tipo_cambio"] == 0
    with pytest.raises(ErrorTipoCambio) as error:
        excel_plantilla([salida], Libro.COMPRAS)
    pendiente = error.value.pendientes[0]
    assert pendiente["serie_numero"] == "E001-143"
    assert pendiente["libro"] == "compras"
    assert pendiente["documento_contraparte"] == "20123456789"


@pytest.mark.parametrize(
    "contradiccion",
    [{"codMoneda": "EUR"}, {"codTipoCDP": "07"}, {"numSerieCDP": "F001"}, {"numCDP": "144"}],
)
def test_rechaza_crudo_de_otra_moneda_o_comprobante(contradiccion):
    fila = documento(crudo={**contradiccion, "tipoCambio": {"mtoTipoCambio": 3.74}})
    assert serializar(fila)["tipo_cambio"] == 0


def test_no_recupera_tc_sunat_para_comprobante_externo():
    fila = documento(crudo={"tipoCambio": {"mtoTipoCambio": 3.74}})
    fila["origen"] = "externo"
    assert serializar(fila)["tipo_cambio"] == 0


def test_exporta_con_tc_recuperado_sin_convertir_dos_veces_los_importes():
    salida = serializar(documento(crudo={"tipoCambio": {"mtoTipoCambio": 3.74}}))
    hoja = load_workbook(excel_plantilla([salida], Libro.COMPRAS)).active
    assert hoja["S4"].value == 4413.2
    assert hoja["W4"].value == 3.74
    assert hoja["AC4"].value == 1180
