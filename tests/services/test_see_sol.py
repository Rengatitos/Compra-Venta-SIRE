"""Tests unitarios para las funciones de soporte y despacho de SEE-SOL en scraping_sunat.py.

Verifica:
- La detección de series SOL (E, EB, EC, ED) vs OSE/Contribuyente (F, B).
- La extracción segura de XML desde archivos ZIP descargados de SUNAT.
- La resolución del RUC del emisor según el libro (compras vs ventas).
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.domain.comprobante import Libro
from app.services import scraping_sunat


class TestDeteccionSerieSol:
    @pytest.mark.parametrize(
        ("serie", "esperado"),
        [
            ("E001", True),
            ("EB01", True),
            ("EC01", True),
            ("ED01", True),
            ("e001", True),
            ("eb01", True),
            (" E001 ", True),
            ("F001", False),
            ("B001", False),
            ("FC01", False),
            ("BC01", False),
            ("001", False),
            ("", False),
            (None, False),
        ],
    )
    def test_identifica_correctamente_las_series_see_sol(self, serie, esperado):
        assert scraping_sunat._es_serie_sol(serie) is esperado


class TestExtraerXmlDeZip:
    def test_extrae_el_xml_contenido_en_el_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("FACTURAE001-192920486339510.XML", b"<Invoice><ID>E001-1929</ID></Invoice>")
            z.writestr("otro.txt", b"ignorar")

        contenido_zip = buf.getvalue()
        extraido = scraping_sunat._extraer_xml_de_zip(contenido_zip)

        assert extraido == b"<Invoice><ID>E001-1929</ID></Invoice>"

    def test_un_xml_plano_sin_zip_se_devuelve_tal_cual(self):
        xml_plano = b"<?xml version='1.0'?><Invoice/>"
        assert scraping_sunat._extraer_xml_de_zip(xml_plano) == xml_plano

        xml_sin_declaracion = b"<Invoice/>"
        assert scraping_sunat._extraer_xml_de_zip(xml_sin_declaracion) == xml_sin_declaracion

    def test_un_contenido_vacio_lanza_error(self):
        with pytest.raises(ValueError, match="vacío"):
            scraping_sunat._extraer_xml_de_zip(b"")

    def test_un_zip_danado_lanza_error(self):
        with pytest.raises(ValueError, match="no es un ZIP válido"):
            scraping_sunat._extraer_xml_de_zip(b"PK\x03\x04invalido")

    def test_un_zip_sin_xml_lanza_error(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("archivo.pdf", b"%PDF-1.4")

        with pytest.raises(ValueError, match="no contiene ningún archivo .xml"):
            scraping_sunat._extraer_xml_de_zip(buf.getvalue())


class TestRucEmisor:
    def test_en_compras_el_emisor_es_el_proveedor(self):
        fac = {"documento_contraparte": "20486339510"}
        assert scraping_sunat._ruc_emisor(fac, Libro.COMPRAS, "20608997106") == "20486339510"

    def test_en_ventas_el_emisor_es_la_empresa_propia(self):
        fac = {"documento_contraparte": "46169303"}
        assert scraping_sunat._ruc_emisor(fac, Libro.VENTAS, "20608997106") == "20608997106"


class TestDespachoPorSerie:
    def test_despacha_a_see_sol_o_ose_segun_la_serie(self, monkeypatch):
        sol_llamado = []
        ose_llamado = []

        def falso_login(*_a, **_k):
            pass

        def falso_abrir_empresas(*_a, **_k):
            pass

        def falso_abrir_see_sol(*_a, **_k):
            pass

        def falso_consultar_see_sol(*_a, **_k):
            sol_llamado.append(True)
            return [{"cantidad": "1.00"}], b"%PDF", b"<xml/>"

        def falso_abrir_ose(*_a, **_k):
            pass

        def falso_consultar_ose(*_a, **_k):
            ose_llamado.append(True)
            return [{"cantidad": "2.00"}], b"%PDF"

        class ContextoFalso:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def new_page(self):
                return PaginaMock()

        class BrowserMock:
            def new_context(self, **_k):
                return ContextoFalso()

            def close(self):
                pass

        class PaginaMock:
            def frame_locator(self, _s):
                return self

            def locator(self, _s):
                return self

        monkeypatch.setattr(scraping_sunat, "_login_con_reintentos", falso_login)
        monkeypatch.setattr(scraping_sunat, "_abrir_modulo_empresas", falso_abrir_empresas)
        monkeypatch.setattr(scraping_sunat, "_abrir_modulo_see_sol", falso_abrir_see_sol)
        monkeypatch.setattr(scraping_sunat, "_consultar_uno_see_sol", falso_consultar_see_sol)
        monkeypatch.setattr(scraping_sunat, "_abrir_consulta", falso_abrir_ose)
        monkeypatch.setattr(scraping_sunat, "_consultar_uno", falso_consultar_ose)

        class PlaywrightMock:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            @property
            def chromium(self):
                return self

            def launch(self, **_k):
                return BrowserMock()

        monkeypatch.setattr(scraping_sunat, "sync_playwright", lambda: PlaywrightMock())

        comprobantes = [
            {"serie_numero": "E001-1929", "serie": "E001", "numero": "1929", "tipo_cp": "01"},
            {"serie_numero": "F001-43318", "serie": "F001", "numero": "43318", "tipo_cp": "01"},
        ]

        xml_descargados = []
        detalles_extraidos = []

        res = scraping_sunat._scrape_detalles(
            "20608997106",
            "USER",
            "PASS",
            comprobantes,
            al_extraer=lambda s, d: detalles_extraidos.append(s),
            al_descargar_xml=lambda s, x: xml_descargados.append(s),
        )

        assert len(sol_llamado) == 1
        assert len(ose_llamado) == 1
        assert "E001-1929" in res
        assert "F001-43318" in res
        assert xml_descargados == ["E001-1929"]
        assert detalles_extraidos == ["E001-1929", "F001-43318"]
