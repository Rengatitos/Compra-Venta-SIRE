"""Estado de la glosa por comprobante: con glosa, sin glosa, en evaluación o pendiente.

El estado combina el tipo de comprobante (qué publica SUNAT), la glosa que ya
se tenga (manual, ítems o leyenda) y si el portal ya se consultó. Es lo que ve
el contador en el listado y en la columna «Estado glosa» del Excel.
"""

import io

import pytest
from openpyxl import load_workbook

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo
from app.services import plantilla_excel, reporte_asociado
from app.services.comprobante_service import serializar
from app.services.glosa import (
    ESTADO_CON_GLOSA,
    ESTADO_EN_EVALUACION,
    ESTADO_PENDIENTE,
    ESTADO_SIN_GLOSA,
    ETIQUETA_ESTADO_GLOSA,
    OBSERVACION_EN_EVALUACION,
    OBSERVACION_SIN_DETALLE_SUNAT,
    OBSERVACION_SIN_GLOSA,
    estado_glosa,
    observacion_glosa,
    obtener_glosa,
)

LEYENDA_BCP = [
    "TARJETA DE DEBITO",
    "Credimas Negocio Juridica",
    "100 *****850 0 **",
    "2026-08-17",
    "TD",
    "SAT",
]


@pytest.mark.parametrize(
    "documento,estado,observacion",
    [
        # Factura consultable: pendiente hasta consultar, sin glosa si el portal no la dio.
        ({"tipo_cp": "01"}, ESTADO_PENDIENTE, ""),
        ({"tipo_cp": "01", "glosa_consultada": True}, ESTADO_SIN_GLOSA, OBSERVACION_SIN_GLOSA),
        ({"tipo_cp": "01", "detalle_sunat": [{"descripcion": "Aceite"}]}, ESTADO_CON_GLOSA, ""),
        # La glosa manual gana siempre, sea cual sea el tipo.
        ({"tipo_cp": "14", "glosa": "Luz de agosto"}, ESTADO_CON_GLOSA, ""),
        # Tipo que SUNAT no publica (12, ticket POS): definitivo, se haya consultado o no.
        ({"tipo_cp": "12"}, ESTADO_SIN_GLOSA, OBSERVACION_SIN_DETALLE_SUNAT),
        (
            {"tipo_cp": "12", "glosa_consultada": True},
            ESTADO_SIN_GLOSA,
            OBSERVACION_SIN_DETALLE_SUNAT,
        ),
        # Tipo por evaluar y códigos fuera del catálogo.
        ({"tipo_cp": "02"}, ESTADO_EN_EVALUACION, OBSERVACION_EN_EVALUACION),
        ({"tipo_cp": "LE"}, ESTADO_EN_EVALUACION, OBSERVACION_EN_EVALUACION),
        # El código llega sin normalizar desde algunas fuentes.
        ({"tipo_cp": 1, "glosa_consultada": True}, ESTADO_SIN_GLOSA, OBSERVACION_SIN_GLOSA),
        # Los 14 tipos "requieren casos" (08, 14…) se tratan como consultables.
        ({"tipo_cp": "08"}, ESTADO_PENDIENTE, ""),
        ({"tipo_cp": "14"}, ESTADO_PENDIENTE, ""),
        # Sin tipo se trata como consultable: los tests y algunas fuentes no lo traen.
        ({}, ESTADO_PENDIENTE, ""),
        ({"glosa_consultada": True}, ESTADO_SIN_GLOSA, OBSERVACION_SIN_GLOSA),
    ],
)
def test_estado_y_observacion_por_tipo(documento, estado, observacion):
    assert estado_glosa(documento) == estado
    assert observacion_glosa(documento) == observacion
    salida = serializar(documento)
    assert salida["estado_glosa"] == estado
    assert salida["observacion"] == observacion


def test_excepcion_por_libro(monkeypatch):
    from app.domain import catalogos

    monkeypatch.setitem(catalogos.SIN_DETALLE_POR_LIBRO, "compras", frozenset({"03"}))
    boleta = {"tipo_cp": "03"}
    assert estado_glosa({**boleta, "libro": "compras"}) == ESTADO_SIN_GLOSA
    assert observacion_glosa({**boleta, "libro": "compras"}) == OBSERVACION_SIN_DETALLE_SUNAT
    assert estado_glosa({**boleta, "libro": "ventas"}) == ESTADO_PENDIENTE


class TestLeyendaComoGlosa:
    def test_la_leyenda_completa_la_glosa_cuando_los_items_no_describen(self):
        documento = {
            "tipo_cp": "01",
            "detalle_sunat": [{"descripcion": ""}],
            "leyenda_sunat": LEYENDA_BCP,
            "glosa_consultada": True,
        }
        assert obtener_glosa(documento) == "TARJETA DE DEBITO / Credimas Negocio Juridica"
        assert estado_glosa(documento) == ESTADO_CON_GLOSA
        assert observacion_glosa(documento) == ""

    def test_los_items_mandan_sobre_la_leyenda(self):
        documento = {
            "detalle_sunat": [{"descripcion": "CONCEPTO DE PAGO:COMISION"}],
            "leyenda_sunat": LEYENDA_BCP,
        }
        assert obtener_glosa(documento) == "CONCEPTO DE PAGO:COMISION"

    @pytest.mark.parametrize(
        "leyenda",
        [
            ["SON DIEZ CON 00/100 SOLES"],
            ["2026-08-17", "17/08/2026"],
            ["100 *****850 0 **"],
            ["TD", "SAT", "-", ""],
            [None, 42],
        ],
    )
    def test_las_lineas_no_descriptivas_no_inventan_glosa(self, leyenda):
        assert obtener_glosa({"leyenda_sunat": leyenda}) == ""

    def test_la_leyenda_viaja_en_la_respuesta(self):
        salida = serializar({"leyenda_sunat": ["TARJETA DE DEBITO", None]})
        assert salida["leyenda_sunat"] == ["TARJETA DE DEBITO"]


@pytest.mark.parametrize("libro", list(Libro))
def test_excel_lleva_columna_estado_glosa_tras_observacion(libro):
    filas = [
        serializar({"tipo_cp": "01", "detalle_sunat": [{"descripcion": "Servicio"}]}),
        serializar({"tipo_cp": "01", "glosa_consultada": True}),
        serializar({"tipo_cp": "12"}),
        serializar({"tipo_cp": "02"}),
        serializar({"tipo_cp": "01"}),
    ]
    salida = plantilla_excel.excel_plantilla(filas, libro)
    hoja = load_workbook(io.BytesIO(salida.getvalue())).active
    cabeceras = [c.value for c in hoja[2] if c.value in ("Observación", "Estado glosa")]
    assert cabeceras == ["Observación", "Estado glosa"]
    columna = next(c.column_letter for c in hoja[2] if c.value == "Estado glosa")
    assert [hoja[f"{columna}{fila}"].value for fila in range(4, 9)] == [
        "Con glosa", "Sin glosa", "Sin glosa", "En evaluación", "Pendiente",
    ]
    observacion = next(c.column_letter for c in hoja[2] if c.value == "Observación")
    assert hoja[f"{observacion}6"].value == OBSERVACION_SIN_DETALLE_SUNAT
    assert hoja[f"{observacion}7"].value == OBSERVACION_EN_EVALUACION


def test_todas_las_etiquetas_tienen_estado():
    assert set(ETIQUETA_ESTADO_GLOSA) == {
        ESTADO_CON_GLOSA, ESTADO_SIN_GLOSA, ESTADO_EN_EVALUACION, ESTADO_PENDIENTE,
    }


@pytest.mark.parametrize("libro", list(Libro))
def test_los_filtros_del_portal_excluyen_los_tipos_sin_detalle(libro):
    for filtro in (
        repo._filtro_pendiente_sunat("empresa", "202608", libro),
        repo._filtro_sin_detalle("empresa", "202608", libro),
    ):
        excluidos = filtro["tipo_cp"]["$nin"]
        assert "12" in excluidos and "01" not in excluidos and "14" not in excluidos
        assert excluidos == sorted(excluidos)


def test_el_reporte_asociado_solo_espera_a_los_consultables():
    registros = {
        Libro.COMPRAS: [
            {"tipo_cp": "12"},                              # sin detalle: no bloquea
            {"tipo_cp": "01", "glosa_consultada": True},    # consultado sin glosa: no bloquea
            {"tipo_cp": "02"},                              # en evaluación: no bloquea
        ],
        Libro.VENTAS: [],
    }
    assert reporte_asociado.estado(registros) == {"habilitado": True, "pendientes": 0}
    registros[Libro.COMPRAS].append({"tipo_cp": "01"})
    assert reporte_asociado.estado(registros) == {"habilitado": False, "pendientes": 1}
