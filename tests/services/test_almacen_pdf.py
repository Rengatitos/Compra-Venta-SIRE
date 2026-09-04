"""La estructura de carpetas es contrato con el auditor, no un detalle interno.

También es el único sitio del backend que construye rutas de escritura a partir
de datos que vienen de SUNAT y de archivos que sube el usuario, así que aquí se
prueba tanto el formato acordado como que nadie pueda salirse del almacén.
"""

from __future__ import annotations

import pytest

from app.domain.comprobante import Libro
from app.services import almacen_pdf


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    """Aísla cada test en su propio directorio."""
    monkeypatch.setattr(almacen_pdf.settings, "SUNAT_DATA_DIR", str(tmp_path))
    return tmp_path


RUC = "20608997106"


class TestRuta:
    def test_sigue_la_estructura_acordada_con_el_cliente(self, almacen):
        ruta = almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "03", "B001", "00001234")

        assert ruta.relative_to(almacen).as_posix() == (
            f"{RUC}/ventas/2026/08/boletas/B001-00001234.pdf"
        )

    def test_una_carpeta_por_tipo_de_comprobante(self):
        assert almacen_pdf.carpeta_de_tipo("01") == "facturas"
        assert almacen_pdf.carpeta_de_tipo("03") == "boletas"
        assert almacen_pdf.carpeta_de_tipo("07") == "notas_credito"
        assert almacen_pdf.carpeta_de_tipo("08") == "notas_debito"

    def test_el_tipo_se_normaliza_antes_de_elegir_la_carpeta(self):
        # SUNAT manda el tipo como "1", como "01" y como entero según el
        # endpoint. Los tres son una factura.
        assert almacen_pdf.carpeta_de_tipo("1") == "facturas"
        assert almacen_pdf.carpeta_de_tipo(1) == "facturas"

    def test_un_tipo_desconocido_no_revienta(self):
        assert almacen_pdf.carpeta_de_tipo("99") == almacen_pdf.CARPETA_POR_DEFECTO
        assert almacen_pdf.carpeta_de_tipo(None) == almacen_pdf.CARPETA_POR_DEFECTO

    def test_el_ruc_separa_las_empresas(self, almacen):
        # La estructura de las anotaciones no llevaba RUC porque la pensaron
        # para una sola empresa. Sin él, dos empresas con el mismo periodo
        # escriben en la misma carpeta y la segunda pisa a la primera.
        una = almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "01", "F001", "1")
        otra = almacen_pdf.ruta_pdf("20123456789", Libro.VENTAS, "202608", "01", "F001", "1")

        assert una != otra

    def test_el_mes_va_con_dos_digitos(self, almacen):
        ruta = almacen_pdf.ruta_pdf(RUC, Libro.COMPRAS, "202601", "01", "F001", "1")

        assert "/2026/01/" in ruta.as_posix()

    def test_un_periodo_invalido_se_rechaza(self):
        with pytest.raises(ValueError):
            almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "2026", "01", "F001", "1")


class TestSaneado:
    def test_limpia_los_caracteres_que_no_valen_en_una_ruta(self, almacen):
        # Series con espacios y con caracteres invisibles han aparecido en los
        # archivos reales; cualquiera de los dos rompe la ruta.
        ruta = almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "01", " F 001 ", "123​")

        assert ruta.name == "F001-123.pdf"

    def test_una_serie_sin_nada_utilizable_se_rechaza(self):
        # Guardar en `.../_.pdf` daría un archivo que nadie puede relacionar
        # con su comprobante: es peor que no tenerlo.
        with pytest.raises(ValueError, match="serie"):
            almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "01", "///", "123")

    def test_los_tramos_de_recorrido_se_rechazan(self):
        with pytest.raises(ValueError, match="separadores"):
            almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "01", "..", "123")

    def test_no_se_puede_salir_del_almacen(self):
        # Un separador en un RUC o en una serie no es algo que limpiar: es
        # una señal de que el dato no es lo que se esperaba.
        with pytest.raises(ValueError, match="separadores"):
            almacen_pdf.ruta_pdf("../../etc", Libro.VENTAS, "202608", "01", "F001", "1")

        with pytest.raises(ValueError, match="separadores"):
            almacen_pdf.ruta_pdf(RUC, Libro.VENTAS, "202608", "01", "../F001", "1")

    def test_una_ruta_guardada_maliciosa_no_resuelve(self):
        with pytest.raises(ValueError, match="se sale del almacén"):
            almacen_pdf.absoluta("../../../etc/passwd")


class TestGuardar:
    def test_escribe_el_archivo_y_crea_las_carpetas(self, almacen):
        destino = almacen_pdf.guardar(
            RUC, Libro.COMPRAS, "202606", "01", "F001", "123", b"%PDF-1.4 x"
        )

        assert destino.read_bytes() == b"%PDF-1.4 x"
        assert destino.parent.is_dir()

    def test_devuelve_la_ruta_relativa_para_guardarla_en_mongo(self, almacen):
        # Se guarda la relativa a propósito: la absoluta ataría la base al
        # punto de montaje y mover el volumen invalidaría los punteros.
        destino = almacen_pdf.guardar(
            RUC, Libro.COMPRAS, "202606", "01", "F001", "123", b"%PDF"
        )

        relativa = almacen_pdf.relativa(destino)
        assert relativa == f"{RUC}/compras/2026/06/facturas/F001-123.pdf"
        assert almacen_pdf.absoluta(relativa) == destino

    def test_un_contenido_vacio_se_rechaza(self):
        with pytest.raises(ValueError, match="contenido"):
            almacen_pdf.guardar(RUC, Libro.VENTAS, "202606", "01", "F001", "1", b"")


class TestListar:
    def test_un_periodo_sin_descargas_devuelve_una_lista_vacia(self):
        assert almacen_pdf.listar(RUC, Libro.VENTAS, "202606") == []

    def test_recoge_los_pdfs_de_todas_las_carpetas_del_periodo(self):
        for tipo, serie in (("01", "F001"), ("03", "B001"), ("07", "FC01")):
            almacen_pdf.guardar(RUC, Libro.VENTAS, "202606", tipo, serie, "1", b"%PDF")

        encontrados = almacen_pdf.listar(RUC, Libro.VENTAS, "202606")

        assert [p.name for p in encontrados] == ["B001-1.pdf", "F001-1.pdf", "FC01-1.pdf"]

    def test_no_mezcla_libros_ni_periodos(self):
        almacen_pdf.guardar(RUC, Libro.VENTAS, "202606", "01", "F001", "1", b"%PDF")
        almacen_pdf.guardar(RUC, Libro.COMPRAS, "202606", "01", "F001", "1", b"%PDF")
        almacen_pdf.guardar(RUC, Libro.VENTAS, "202607", "01", "F001", "1", b"%PDF")

        assert len(almacen_pdf.listar(RUC, Libro.VENTAS, "202606")) == 1
        assert len(almacen_pdf.listar(RUC, Libro.COMPRAS, "202606")) == 1

    def test_guardar_xml_no_es_recogido_por_listar(self, almacen):
        almacen_pdf.guardar(
            RUC,
            Libro.VENTAS,
            "202606",
            "01",
            "E001",
            "1929",
            b"<xml/>",
            extension="xml",
            subcarpeta="xml",
        )
        ruta = almacen_pdf.ruta_pdf(
            RUC,
            Libro.VENTAS,
            "202606",
            "01",
            "E001",
            "1929",
            extension="xml",
            subcarpeta="xml",
        )
        assert ruta.relative_to(almacen).as_posix() == f"{RUC}/ventas/2026/06/xml/E001-1929.xml"
        assert ruta.is_file()
        assert almacen_pdf.listar(RUC, Libro.VENTAS, "202606") == []
