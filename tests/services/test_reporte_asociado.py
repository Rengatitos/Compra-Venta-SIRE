"""El reporte asociado entrega el ZIP o identifica el comprobante sin TC."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.api.v1.deps import empresa_actual
from app.api.v1.routes import reporte_asociado as ruta
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.services import reporte_asociado

RUC = "20000000000"
PERIODO = "202406"
URL = f"/empresas/{RUC}/periodos/{PERIODO}/reporte-asociado"


def comprobante(libro, tipo_cambio=None, raw_sire=None):
    return {
        "libro": libro.value,
        "origen": "sire",
        "serie_numero": "F001-1",
        "tipo_cp": "01",
        "serie": "F001",
        "numero": "1",
        "tipo_doc_identidad": "6",
        "documento_contraparte": "20000000001",
        "razon_social": "Empresa de prueba",
        "fecha_emision": "2024-06-03",
        "moneda": "USD",
        "tipo_cambio": tipo_cambio,
        "porcentaje_igv": 18,
        "base_imponible": 100,
        "igv": 18,
        "base_imponible_dg": 100,
        "igv_dg": 18,
        "total": 118,
        "glosa": "Servicio de prueba",
        "extra": {"raw_sire": raw_sire} if raw_sire is not None else {},
    }


@pytest.fixture
def contexto(monkeypatch, tmp_path):
    empresa = {"_id": "empresa-de-prueba", "ruc": RUC, "usuario": "PRUEBA"}
    filas = {Libro.COMPRAS: [], Libro.VENTAS: []}
    temporales = []
    carpeta_temporal = tmp_path / "temporales"
    carpeta_temporal.mkdir()

    async def listar(db, empresa_id, periodo, libro, skip, limit):
        assert empresa_id == empresa["_id"]
        assert periodo == PERIODO
        return filas[libro][skip:skip + limit]

    crear_temporal = reporte_asociado.tempfile.NamedTemporaryFile

    def temporal(**kwargs):
        archivo = crear_temporal(dir=carpeta_temporal, **kwargs)
        temporales.append(Path(archivo.name))
        return archivo

    monkeypatch.setattr(ruta.repo_periodos, "obtener", AsyncMock(return_value={"periodo": PERIODO}))
    monkeypatch.setattr(reporte_asociado.comprobantes, "listar", listar)
    monkeypatch.setattr(
        reporte_asociado.pagos_vouchers, "adjuntar_pagos", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        reporte_asociado.almacen_pdf.settings, "SUNAT_DATA_DIR", str(tmp_path / "pdfs")
    )
    monkeypatch.setattr(reporte_asociado.tempfile, "NamedTemporaryFile", temporal)

    app = FastAPI()
    app.include_router(ruta.router, prefix="/empresas/{ruc}/periodos/{periodo}")
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[empresa_actual] = lambda: empresa
    with TestClient(app) as cliente:
        yield SimpleNamespace(cliente=cliente, filas=filas, temporales=temporales)


@pytest.mark.parametrize("libro", [Libro.COMPRAS, Libro.VENTAS])
@pytest.mark.parametrize("tipo_cambio", [None, 0])
def test_sin_tc_devuelve_422_con_el_comprobante_y_borra_el_zip(contexto, libro, tipo_cambio):
    contexto.filas[libro].append(comprobante(libro, tipo_cambio))

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 422
    detalle = respuesta.json()["detail"]
    assert "sin tipo de cambio SUNAT" in detalle["mensaje"]
    [pendiente] = detalle["comprobantes_sin_tc"]
    assert pendiente["serie_numero"] == "F001-1"
    assert pendiente["moneda"] == "USD"
    assert pendiente["libro"] == libro.value
    assert pendiente["documento_contraparte"] == "20000000001"
    assert pendiente["razon_social"] == "Empresa de prueba"
    assert len(contexto.temporales) == 1
    assert not contexto.temporales[0].exists()


@pytest.mark.parametrize("como_json", [False, True])
def test_el_zip_recupera_tc_de_sunat_y_contiene_ambos_libros_y_pdfs(contexto, como_json):
    raw_sire = {"mtoTipoCambio": "3.740", "codMoneda": "USD"}
    if como_json:
        raw_sire = json.dumps(raw_sire)
    for libro in (Libro.COMPRAS, Libro.VENTAS):
        contexto.filas[libro].append(comprobante(libro, raw_sire=raw_sire))
        pdf = reporte_asociado.almacen_pdf.ruta_pdf(RUC, libro, PERIODO, "01", "F001", "1")
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF prueba")

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/zip"
    assert "PRUEBA-JUNIO2024.zip" in respuesta.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as archivo:
        assert set(archivo.namelist()) == {
            "PRUEBA-JUNIO2024.xlsx",
            "comprobantes compra/",
            "comprobantes compra/facturas/F001-1.pdf",
            "comprobantes venta/",
            "comprobantes venta/facturas/F001-1.pdf",
        }
        libro = load_workbook(io.BytesIO(archivo.read("PRUEBA-JUNIO2024.xlsx")))
        assert libro.sheetnames == [
            "Correlatividad cp", "Registro de ventas", "Registro de compras"
        ]
        assert libro["Registro de compras"]["W4"].value == 3.74
        assert libro["Registro de ventas"]["Q4"].value == 3.74
        assert libro["Registro de compras"]["S4"].value == 118
        assert libro["Registro de ventas"]["P4"].value == 118
    assert len(contexto.temporales) == 1
    assert not contexto.temporales[0].exists()


def test_glosa_pendiente_sigue_bloqueando_la_descarga(contexto):
    fila = comprobante(Libro.COMPRAS, tipo_cambio=3.74)
    fila.pop("glosa")
    contexto.filas[Libro.COMPRAS].append(fila)

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 409
    assert "Completa las glosas" in respuesta.json()["detail"]
    assert contexto.temporales == []


def comprobante_en_cero(libro, tipo_cambio=None):
    fila = comprobante(libro, tipo_cambio)
    fila.update(
        base_imponible=0, igv=0, base_imponible_dg=0, igv_dg=0, total=0
    )
    return fila


@pytest.mark.parametrize("tipo_cambio", [None, 0])
def test_el_zip_conserva_comprobantes_usd_en_cero_sin_inventar_tc(contexto, tipo_cambio):
    for libro in (Libro.COMPRAS, Libro.VENTAS):
        contexto.filas[libro].append(comprobante_en_cero(libro, tipo_cambio))

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 200
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as archivo:
        libro = load_workbook(io.BytesIO(archivo.read("PRUEBA-JUNIO2024.xlsx")))
        for nombre, numero, tc, moneda, equivalente, glosa in (
            ("Registro de compras", "F4", "W4", "AB4", "AC4", "AS4"),
            ("Registro de ventas", "E4", "Q4", "V4", "W4", "AM4"),
        ):
            hoja = libro[nombre]
            assert hoja["D4"].value == "F001"
            assert hoja[numero].value == 1
            assert hoja[glosa].value == "SERVICIO DE PRUEBA"
            assert hoja[moneda].value == "D"
            assert hoja[tc].value is None
            assert hoja[equivalente].value is None
    assert len(contexto.temporales) == 1
    assert not contexto.temporales[0].exists()


@pytest.mark.parametrize("libro", [Libro.COMPRAS, Libro.VENTAS])
@pytest.mark.parametrize(
    ("campo", "importe"),
    [("base_imponible", 100), ("igv", 18), ("otros_tributos", -5)],
)
def test_total_cero_con_otros_importes_sigue_bloqueando_sin_tc(contexto, libro, campo, importe):
    fila = comprobante_en_cero(libro)
    fila[campo] = importe
    contexto.filas[libro].append(fila)

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 422
    [pendiente] = respuesta.json()["detail"]["comprobantes_sin_tc"]
    assert pendiente["serie_numero"] == "F001-1"
    assert pendiente["libro"] == libro.value
    assert pendiente["monto_original"] == "0.0"
    assert len(contexto.temporales) == 1
    assert not contexto.temporales[0].exists()


def comprobante_de_baja(libro):
    fila = comprobante_en_cero(libro, tipo_cambio=0)
    fila.update(serie_numero="F001-2", numero="2")
    fila.pop("glosa")
    fila["extra"]["raw_sire"] = {
        "codEstadoComprobante": "2",
        "desEstadoComprobante": "BAJA",
        "codMoneda": "USD",
        "mtoTipoCambio": "0.000",
    }
    return fila


@pytest.mark.parametrize("libro", [Libro.COMPRAS, Libro.VENTAS])
def test_la_baja_no_bloquea_ni_se_incluye_en_excel_control_o_pdfs(contexto, libro):
    contexto.filas[libro].extend([
        comprobante(libro, tipo_cambio=3.74), comprobante_de_baja(libro)
    ])
    for numero in ("1", "2", "99"):
        pdf = reporte_asociado.almacen_pdf.ruta_pdf(
            RUC, libro, PERIODO, "01", "F001", numero
        )
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF prueba")
    pdf_legacy = (
        reporte_asociado.almacen_pdf.raiz_periodo(RUC, libro, PERIODO) / "legacy/F001-2.pdf"
    )
    pdf_legacy.parent.mkdir()
    pdf_legacy.write_bytes(b"%PDF baja anterior")
    contexto.filas[libro][1]["pdf_sunat"] = {
        "ruta": reporte_asociado.almacen_pdf.relativa(pdf_legacy)
    }

    estado = contexto.cliente.get(f"{URL}/estado")
    assert estado.status_code == 200
    assert estado.json() == {"habilitado": True, "pendientes": 0}

    respuesta = contexto.cliente.get(URL)

    assert respuesta.status_code == 200
    carpeta = "comprobantes compra" if libro is Libro.COMPRAS else "comprobantes venta"
    nombre_hoja = "Registro de compras" if libro is Libro.COMPRAS else "Registro de ventas"
    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as archivo:
        assert f"{carpeta}/facturas/F001-1.pdf" in archivo.namelist()
        assert f"{carpeta}/facturas/F001-2.pdf" not in archivo.namelist()
        assert f"{carpeta}/legacy/F001-2.pdf" not in archivo.namelist()
        # Los PDFs adicionales del periodo se conservan aunque no estén en la base.
        assert f"{carpeta}/facturas/F001-99.pdf" in archivo.namelist()
        wb = load_workbook(io.BytesIO(archivo.read("PRUEBA-JUNIO2024.xlsx")))
        assert wb.sheetnames == ["Correlatividad cp", nombre_hoja]
        control = wb["Correlatividad cp"]
        assert control.max_row == 4
        assert [control[f"{columna}4"].value for columna in "FGH"] == [1, 1, 1]
        hoja = wb[nombre_hoja]
        numero = "F" if libro is Libro.COMPRAS else "E"
        total = "S" if libro is Libro.COMPRAS else "P"
        assert hoja[f"{numero}4"].value == 1
        assert hoja[f"{numero}5"].value is None
        assert hoja[f"{total}4"].value == 118
        assert hoja[f"{total}5"].value == f"=SUM({total}4:{total}4)"
    assert len(contexto.temporales) == 1
    assert not contexto.temporales[0].exists()


@pytest.mark.parametrize("libro", [Libro.COMPRAS, Libro.VENTAS])
def test_un_periodo_solo_con_bajas_no_habilita_el_reporte(contexto, libro):
    contexto.filas[libro].append(comprobante_de_baja(libro))

    respuesta = contexto.cliente.get(f"{URL}/estado")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"habilitado": False, "pendientes": 0}
    assert contexto.temporales == []


@pytest.mark.parametrize("libro", [Libro.COMPRAS, Libro.VENTAS])
def test_la_glosa_pendiente_de_un_activo_sigue_bloqueando_junto_a_una_baja(contexto, libro):
    activo = comprobante(libro, tipo_cambio=3.74)
    activo.pop("glosa")
    contexto.filas[libro].extend([activo, comprobante_de_baja(libro)])

    respuesta = contexto.cliente.get(f"{URL}/estado")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"habilitado": False, "pendientes": 1}
