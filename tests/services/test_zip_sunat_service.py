import asyncio
import zipfile
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.routes import pdfs
from app.domain.comprobante import Libro
from app.domain.jobs import EstadoJob, Job, TipoJob
from app.services import zip_sunat_service as servicio

EMPRESA = {"_id": "empresa", "ruc": "20123456789", "usuario": "KP610202"}
JOB = "a" * 32


def documento(identificador, serie="E001", emisor="20987654321"):
    return {
        "_id": identificador,
        "serie": serie,
        "numero": "1",
        "tipo_cp": "01",
        "serie_numero": f"{serie}-1",
        "documento_contraparte": emisor,
        "pdf_sunat": {"ruta": "archivo_antiguo.pdf"},
    }


def test_zip_nuevo_ambos_registros_colisiones_y_faltantes(tmp_path, monkeypatch):
    monkeypatch.setattr(servicio.almacen_pdf, "raiz", lambda: tmp_path)
    compras = [documento("1"), documento("2", emisor="20111111111"), documento("3", "F001")]
    ventas = [documento("4", "EB01")]

    async def listar(*args, libro, skip, limit):
        return (compras if libro == Libro.COMPRAS else ventas)[skip : skip + limit]

    llamadas = []

    async def scrape(empresa, filas, **kwargs):
        llamadas.extend(filas)
        for fila in filas:
            if fila["_id"] != "3":
                kwargs["al_descargar"](
                    fila["serie_numero"], b"%PDF-1.4 nuevo " + fila["_id"].encode()
                )

    monkeypatch.setattr(servicio.comprobantes, "listar", listar)
    monkeypatch.setattr(servicio.scraping_sunat, "obtener_detalles", scrape)
    resultado = asyncio.run(servicio.preparar(None, EMPRESA, "202608", JOB, AsyncMock()))
    assert resultado["descargados"] == 3
    assert resultado["sin_pdf"] == 1
    assert len(llamadas) == 4  # También vuelve a consultar los que tenían PDF guardado.
    assert resultado["nombre"].endswith("_KP610202.zip")
    with zipfile.ZipFile(servicio.ruta_archivo(EMPRESA["ruc"], JOB)) as archivo:
        nombres = archivo.namelist()
        assert "comprobantes compra/" in nombres
        assert "comprovantes venta/" in nombres
        contenidos = [archivo.read(n) for n in nombres if n.endswith(".pdf")]
        assert set(contenidos) == {b"%PDF-1.4 nuevo 1", b"%PDF-1.4 nuevo 2", b"%PDF-1.4 nuevo 4"}
        assert "F001-1" in archivo.read("faltantes.csv").decode("utf-8-sig")


def test_recorre_mas_de_una_pagina_y_elimina_zip_si_falla(tmp_path, monkeypatch):
    monkeypatch.setattr(servicio.almacen_pdf, "raiz", lambda: tmp_path)
    filas = [documento(str(i), f"F{i:03}") for i in range(501)]

    async def listar(*args, libro, skip, limit):
        return filas[skip : skip + limit] if libro == Libro.COMPRAS else []

    async def scrape(empresa, comprobantes, **kwargs):
        assert len(comprobantes) == 501
        raise RuntimeError("SUNAT sin conexión")

    monkeypatch.setattr(servicio.comprobantes, "listar", listar)
    monkeypatch.setattr(servicio.scraping_sunat, "obtener_detalles", scrape)
    with pytest.raises(RuntimeError):
        asyncio.run(servicio.preparar(None, EMPRESA, "202608", JOB, AsyncMock()))
    assert not servicio.ruta_archivo(EMPRESA["ruc"], JOB).exists()


@pytest.mark.parametrize(
    "ruc,periodo,estado,codigo",
    [
        ("20999999999", "202608", EstadoJob.COMPLETADO, 404),
        (EMPRESA["ruc"], "202607", EstadoJob.COMPLETADO, 404),
        (EMPRESA["ruc"], "202608", EstadoJob.EN_PROGRESO, 409),
    ],
)
def test_zip_restringido_a_empresa_periodo_y_job_completado(
    monkeypatch, ruc, periodo, estado, codigo
):
    job = Job(
        job_id=JOB,
        tipo=TipoJob.DESCARGA_PDFS,
        ruc=ruc,
        periodo=periodo,
        estado=estado,
        resultado={"zip_completo": True},
    )
    monkeypatch.setattr(pdfs.jobs_service, "obtener", AsyncMock(return_value=job))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(pdfs.descargar_zip_completo(JOB, "202608", EMPRESA, None))
    assert exc.value.status_code == codigo
