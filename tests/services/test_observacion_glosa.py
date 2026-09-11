import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

import pytest
from openpyxl import load_workbook

from app.domain.comprobante import Libro
from app.services import detalle_service, plantilla_excel, scraping_sunat
from app.services.comprobante_service import serializar
from app.services.glosa import OBSERVACION_SIN_GLOSA, observacion_glosa


@pytest.mark.parametrize(
    "documento,esperado",
    [
        ({}, ""),
        ({"glosa_consultada": False}, ""),
        ({"glosa_consultada": True}, OBSERVACION_SIN_GLOSA),
        ({"glosa_consultada": True, "detalle_sunat": []}, OBSERVACION_SIN_GLOSA),
        ({"glosa_consultada": True, "detalle_sunat": [{"descripcion": "Servicio real"}]}, ""),
        ({"glosa_consultada": True, "glosa": "Texto ingresado por el usuario"}, ""),
    ],
)
def test_observacion_solo_tras_consulta_sin_glosa(documento, esperado):
    assert observacion_glosa(documento) == esperado
    assert serializar(documento)["observacion"] == esperado
    if esperado:
        assert serializar(documento)["glosa"] == ""


@pytest.mark.parametrize("libro", list(Libro))
def test_excel_observacion_separada_de_glosa(libro):
    filas = [
        serializar({"glosa_consultada": True}),
        serializar({}),
        serializar({"glosa_consultada": True, "glosa": "SERVICIO REAL"}),
    ]
    salida = plantilla_excel.excel_plantilla(filas, libro)
    hoja = load_workbook(io.BytesIO(salida.getvalue())).active
    columna = next(c.column_letter for c in hoja[2] if c.value == "Observación")
    assert hoja[f"{columna}4"].value == OBSERVACION_SIN_GLOSA
    assert hoja[f"{columna}5"].value is None
    assert hoja[f"{columna}6"].value is None
    glosa = "AS" if libro == Libro.COMPRAS else "AM"
    assert hoja[f"{glosa}4"].value is None
    assert hoja[f"{glosa}6"].value == "SERVICIO REAL"


def test_scraper_no_marca_documentos_omitidos(monkeypatch):
    pw = MagicMock()
    monkeypatch.setattr(scraping_sunat, "sync_playwright", lambda: pw)
    monkeypatch.setattr(scraping_sunat, "_login_con_reintentos", lambda *a: None)
    monkeypatch.setattr(scraping_sunat, "_abrir_modulo_empresas", lambda *a: None)
    monkeypatch.setattr(scraping_sunat, "_abrir_consulta", lambda *a: None)
    monkeypatch.setattr(
        scraping_sunat,
        "_consultar_uno",
        MagicMock(side_effect=scraping_sunat.ComprobanteNoEncontrado("F001-1")),
    )
    consultados = []
    filas = [
        {"_id": "1", "serie": "F001", "numero": "1", "serie_numero": "F001-1"},
        {"_id": "2", "serie": "", "numero": "2"},
    ]
    scraping_sunat._scrape_detalles(
        "ruc", "usuario", "clave", filas, al_consultar=consultados.append
    )
    assert consultados == [filas[0]]


def test_servicio_marca_solo_consultados_no_todo_el_lote(monkeypatch):
    repo = detalle_service.repo_comprobantes
    filas = [{"_id": "1", "serie_numero": "F001-1"}, {"_id": "2", "serie_numero": "F001-2"}]
    monkeypatch.setattr(repo, "listar_pendientes_sunat", AsyncMock(return_value=filas))
    monkeypatch.setattr(repo, "contar_pendientes_sunat", AsyncMock(return_value=300))
    marcar = AsyncMock()
    monkeypatch.setattr(repo, "marcar_consulta_glosa", marcar)

    async def extraer(*args, **kwargs):
        kwargs["al_consultar"](filas[0])
        return {}

    monkeypatch.setattr(scraping_sunat, "obtener_detalles", extraer)
    asyncio.run(
        detalle_service.extraer(
            None, {"_id": "empresa", "ruc": "ruc"}, "202608", Libro.VENTAS, AsyncMock()
        )
    )
    marcar.assert_awaited_once_with(None, "empresa", "202608", Libro.VENTAS, ["1"])
