import asyncio
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.services import detracciones_service as service
from app.services.sunat import detracciones as api

RUC = "20123456789"
NPD = {
    "numero": "000123",
    "cabecera": {"estado": "No Vigente", "importe": 270},
    "detalle": {"listadepositoDetInternet": [{"numComprobante": "753"}]},
}


@pytest.mark.parametrize("marca, esperado", [("D", True), ("", False), (None, False)])
def test_disponibilidad_considera_todo_el_periodo(monkeypatch, marca, esperado):
    from app.api.v1.routes import detracciones as rutas

    documentos = [{"extra": {}} for _ in range(100)]
    documentos.append({"extra": {"raw_sire": json.dumps({"indDetraccion": marca})}})
    monkeypatch.setattr(rutas.repo, "listar_todos_compras", AsyncMock(return_value=documentos))
    assert asyncio.run(rutas.disponibilidad("202608", {"_id": "empresa"}, None)) == {
        "disponible": esperado
    }


def test_intervalos_no_pierden_dia_31():
    assert list(api.intervalos("202608")) == [
        ("01/08/2026", "31/08/2026"),
    ]
    assert list(api.intervalos("202402")) == [("01/02/2024", "29/02/2024")]


def test_scraper_consulta_solo_npds_y_un_detalle_por_numero(monkeypatch):
    playwright = MagicMock()
    browser = playwright.__enter__.return_value.chromium.launch.return_value
    monkeypatch.setattr(api, "sync_playwright", lambda: playwright)
    monkeypatch.setattr(api, "_abrir", Mock(return_value=Mock()))
    numero = "0001960265544"
    listar = Mock(return_value=[{"numNpd": numero, "numRuc": RUC}] * 2)
    monkeypatch.setattr(api, "_listar", listar)
    pasos = []
    monkeypatch.setattr(api, "_detalle", lambda *args: pasos.append("detalle") or {})
    monkeypatch.setattr(api, "_pdf", lambda *args: pasos.append("pdf") or "npd.pdf")
    resultado = api._scrape(RUC, "usuario", "clave", "202608")
    assert len(resultado["npds"]) == 1
    listar.assert_called_once()
    assert pasos == ["detalle", "pdf"]
    assert resultado["npds"][0]["pdf_ruta"] == "npd.pdf"
    browser.close.assert_called_once()


def test_guarda_npds_en_periodo_sin_cruzar_comprobantes(monkeypatch):
    monkeypatch.setattr(
        service.repo_periodos, "obtener", AsyncMock(return_value={"periodo": "202608"})
    )
    guardar = AsyncMock()
    monkeypatch.setattr(service.repo_periodos, "guardar_npds", guardar)
    monkeypatch.setattr(api, "obtener", AsyncMock(return_value={"npds": [NPD]}))
    resultado = asyncio.run(
        service.consultar(None, {"_id": "empresa", "ruc": RUC}, "202608", AsyncMock())
    )
    assert resultado == {"npds_consultados": 1, "pdfs_descargados": 0}
    assert guardar.call_args.args[1:4] == ("empresa", "202608", [NPD])


def test_error_sunat_no_borra_npds_previos(monkeypatch):
    monkeypatch.setattr(
        service.repo_periodos, "obtener", AsyncMock(return_value={"periodo": "202608"})
    )
    guardar = AsyncMock()
    monkeypatch.setattr(service.repo_periodos, "guardar_npds", guardar)
    monkeypatch.setattr(api, "obtener", AsyncMock(side_effect=api.SesionSolError("Sesi?n vencida")))
    with pytest.raises(api.SesionSolError):
        asyncio.run(service.consultar(None, {"_id": "empresa", "ruc": RUC}, "202608", AsyncMock()))
    guardar.assert_not_called()


def test_zip_contiene_solo_pdf(monkeypatch, tmp_path):
    pdf = tmp_path / "npd.pdf"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    monkeypatch.setattr(service.almacen_pdf, "absoluta", lambda _: pdf)
    with zipfile.ZipFile(
        io.BytesIO(service.armar_zip([{**NPD, "pdf_ruta": "npd.pdf"}]))
    ) as archivo:
        assert archivo.namelist() == ["npd_000123.pdf"]
        assert archivo.read("npd_000123.pdf") == pdf.read_bytes()


def test_zip_sin_pdf_no_descarga_archivo_vacio():
    with pytest.raises(FileNotFoundError):
        service.armar_zip([NPD])


def test_listado_y_descarga_salen_del_periodo_sin_consulta_sunat(monkeypatch):
    from app.api.v1.routes import detracciones as rutas

    obtener = AsyncMock(return_value={"npds": [NPD], "npds_consultado_en": "2026-09-07"})
    monkeypatch.setattr(service.repo_periodos, "obtener", obtener)
    remoto = AsyncMock()
    monkeypatch.setattr(api, "obtener", remoto)
    listado = asyncio.run(rutas.listar_npds("202608", {"_id": "empresa"}, None))
    assert listado["npds"] == [NPD]
    obtener.assert_awaited_with(None, "empresa", "202608")
    remoto.assert_not_called()


def test_error_playwright_no_expone_cabeceras(monkeypatch):
    playwright = MagicMock()
    monkeypatch.setattr(api, "sync_playwright", lambda: playwright)
    monkeypatch.setattr(api, "_abrir", Mock(side_effect=api.PlaywrightError("IdCache: secreto")))
    with pytest.raises(api.SesionSolError) as error:
        api._scrape(RUC, "usuario", "clave", "202608")
    assert "secreto" not in str(error.value)
    assert error.value.__suppress_context__
    playwright.__enter__.return_value.chromium.launch.return_value.close.assert_called_once()


@pytest.mark.parametrize("libro, automatico", [("compras", True), ("ventas", False)])
def test_propuesta_encola_detracciones_despues_de_guardar(monkeypatch, libro, automatico):
    from fastapi import BackgroundTasks
    from starlette.requests import Request

    from app.api.v1.routes import propuesta
    from app.domain.comprobante import Libro

    sincronizar = AsyncMock(return_value={"nuevos": 1, "actualizados": 0, "mensaje": "OK"})
    encolar = AsyncMock(return_value=SimpleNamespace(job_id="job"))
    monkeypatch.setattr(propuesta.propuesta_service, "sincronizar", sincronizar)
    monkeypatch.setattr(propuesta.detracciones_service, "encolar", encolar)
    respuesta = asyncio.run(
        propuesta.sincronizar_propuesta.__wrapped__(
            Request({"type": "http"}),
            BackgroundTasks(),
            periodo="202608",
            libro=Libro(libro),
            empresa={"ruc": RUC},
            db=None,
        )
    )
    assert encolar.await_count == int(automatico)
    assert ("detracciones_job_id" in respuesta["datos"]) is automatico


def test_descarga_rechaza_ruc_de_otra_empresa(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.deps import empresa_autenticada
    from app.api.v1.routes.detracciones import router

    app = FastAPI()
    app.include_router(router, prefix="/empresas/{ruc}/periodos/{periodo}/detracciones")
    app.dependency_overrides[empresa_autenticada] = lambda: {"ruc": RUC, "_id": "empresa"}
    listar = AsyncMock()
    monkeypatch.setattr(service.repo_periodos, "obtener", listar)
    respuesta = TestClient(app).get("/empresas/20000000000/periodos/202608/detracciones/zip")
    assert respuesta.status_code == 403
    listar.assert_not_called()


def test_seleccionar_acepta_respuesta_vacia():
    context = Mock()
    response = context.request.post.return_value
    response.ok = True
    response.body.return_value = b""
    api._seleccionar(context, "0001960265544")
    assert context.request.post.call_args.kwargs["params"] == {
        "action": "consultarNPD",
        "num_npd": "0001960265544",
    }
    response.json.assert_not_called()
    response.dispose.assert_called_once()


def test_listado_sin_codigo_http_en_json():
    respuesta = Mock(ok=True)
    respuesta.json.return_value = {"resultado": []}
    assert api._leer_listado(respuesta) == []


def test_detalle_rechaza_documento_de_otra_sesion():
    with pytest.raises(api.SesionSolError):
        api._validar_detalle({"campos": {}, "tabla": True}, "0001960265544", RUC)
