"""El ZIP es el entregable del auditor, así que se prueba su contenido: los
PDFs con la jerarquía que se le prometió, y el manifiesto que permite cruzarlos
con el registro. Sin el manifiesto es una bolsa de archivos sin trazabilidad."""

from __future__ import annotations

import csv
import io
import os
import zipfile
from datetime import datetime

import pytest

from app.api.v1.routes import pdfs
from app.domain.comprobante import Libro
from app.services import almacen_pdf

RUC = "20608997106"


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen_pdf.settings, "SUNAT_DATA_DIR", str(tmp_path))
    return tmp_path


FILAS = [
    {
        "serie_numero": "F001-1",
        "tipo_cp": "01",
        "fecha_emision": datetime(2026, 6, 15),
        "documento_contraparte": "20129646099",
        "razon_social": "ELECTROCENTRO S.A.",
        "total": "118.00",
        "pdf_sunat": {"ruta": f"{RUC}/compras/2026/06/facturas/F001-1.pdf", "bytes": 4},
    },
    {
        "serie_numero": "F001-2",
        "tipo_cp": "01",
        "fecha_emision": datetime(2026, 6, 20),
        "documento_contraparte": "20100017491",
        "razon_social": "OTRO PROVEEDOR SAC",
        "total": "59.00",
        # Este se quedó sin respaldo: tiene que aparecer igual en el
        # manifiesto, marcado, o el auditor no sabe que falta.
    },
]


def _zip_de(filas, pdfs_guardados):
    for tipo, serie, numero in pdfs_guardados:
        almacen_pdf.guardar(RUC, Libro.COMPRAS, "202606", tipo, serie, numero, b"%PDF")

    base = almacen_pdf.raiz_periodo(RUC, Libro.COMPRAS, "202606")
    ruta = pdfs._armar_zip(
        almacen_pdf.listar(RUC, Libro.COMPRAS, "202606"), base, pdfs._manifiesto(filas)
    )
    try:
        with open(ruta, "rb") as archivo:
            return zipfile.ZipFile(io.BytesIO(archivo.read()))
    finally:
        os.unlink(ruta)


def _manifiesto_de(zf):
    texto = zf.read("manifiesto.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


class TestContenido:
    def test_conserva_la_jerarquia_de_carpetas(self):
        zf = _zip_de(FILAS, [("01", "F001", "1"), ("03", "B001", "9")])

        nombres = sorted(n for n in zf.namelist() if n.endswith(".pdf"))
        assert nombres == ["boletas/B001-9.pdf", "facturas/F001-1.pdf"]

    def test_los_pdfs_llegan_intactos(self):
        zf = _zip_de(FILAS, [("01", "F001", "1")])

        assert zf.read("facturas/F001-1.pdf") == b"%PDF"

    def test_incluye_el_manifiesto(self):
        zf = _zip_de(FILAS, [("01", "F001", "1")])

        assert "manifiesto.csv" in zf.namelist()


class TestManifiesto:
    def test_una_fila_por_comprobante_del_registro(self):
        zf = _zip_de(FILAS, [("01", "F001", "1")])

        assert [f["serie_numero"] for f in _manifiesto_de(zf)] == ["F001-1", "F001-2"]

    def test_relaciona_el_comprobante_con_su_archivo(self):
        zf = _zip_de(FILAS, [("01", "F001", "1")])
        fila = _manifiesto_de(zf)[0]

        assert fila["ruta_pdf"] == f"{RUC}/compras/2026/06/facturas/F001-1.pdf"
        assert fila["estado"] == "descargado"
        assert fila["razon_social"] == "ELECTROCENTRO S.A."
        assert fila["total"] == "118.00"

    def test_marca_los_comprobantes_sin_respaldo(self):
        # El hueco tiene que ser visible: un comprobante que no aparece es
        # indistinguible de uno que nunca existió.
        zf = _zip_de(FILAS, [("01", "F001", "1")])
        fila = _manifiesto_de(zf)[1]

        assert fila["ruta_pdf"] == ""
        assert fila["estado"] == "sin_pdf"

    def test_la_fecha_va_en_iso(self):
        zf = _zip_de(FILAS, [("01", "F001", "1")])

        assert _manifiesto_de(zf)[0]["fecha_emision"] == "2026-06-15"

    def test_lleva_bom_para_que_excel_no_parta_las_tildes(self):
        assert pdfs._manifiesto(FILAS).startswith(b"\xef\xbb\xbf")

    def test_sin_comprobantes_queda_solo_la_cabecera(self):
        texto = pdfs._manifiesto([]).decode("utf-8-sig")

        assert texto.strip().splitlines() == [";".join(pdfs.CABECERA_MANIFIESTO)]
