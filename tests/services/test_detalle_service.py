"""La extracción es una sola pasada por el portal SOL: por cada comprobante se
lleva el detalle de ítems y el PDF, conservando los datos de SUNAT. El avance
nace en el hilo de Playwright y tiene que llegar al job, que vive en el loop:
es el punto donde antes se perdía y el trabajo se pasaba minutos en `0 / N`."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.comprobante import Libro
from app.services import almacen_pdf, detalle_service

EMPRESA = {"_id": "abc123", "ruc": "20608997106"}
PENDIENTES = [
    {"_id": "1", "serie_numero": "F001-1", "serie": "F001", "numero": "1", "tipo_cp": "01"},
    {"_id": "2", "serie_numero": "F001-2", "serie": "F001", "numero": "2", "tipo_cp": "01"},
    {"_id": "3", "serie_numero": "F001-3", "serie": "F001", "numero": "3", "tipo_cp": "01"},
]


@pytest.fixture(autouse=True)
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(almacen_pdf.settings, "SUNAT_DATA_DIR", str(tmp_path))
    return tmp_path


def _correr(
    monkeypatch,
    pendientes,
    total_en_bd=None,
    corta_en=None,
    sin_pdf=(),
    libro=Libro.COMPRAS,
):
    """Ejecuta `extraer` con el repositorio y el scraping simulados."""
    reportes: list[tuple[int, int, str]] = []
    guardados: list[str] = []
    xml_guardados: list[str] = []
    punteros_pdf: list[tuple[str, str, int]] = []
    clasificados: list[str] = []
    libros_pedidos: list[Libro] = []

    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        reportes.append((actual, total, mensaje))

    async def listar_pendientes_sunat(db, empresa_id, periodo, libro_pedido):
        libros_pedidos.append(libro_pedido)
        return pendientes

    async def contar_pendientes_sunat(db, empresa_id, periodo, libro_pedido):
        return len(pendientes) if total_en_bd is None else total_en_bd

    async def guardar_detalle_sunat(db, empresa_id, periodo, libro_pedido, serie_numero, detalle):
        libros_pedidos.append(libro_pedido)
        guardados.append(serie_numero)

    async def guardar_xml_sunat(db, empresa_id, periodo, libro_pedido, serie_numero, ruta, bytes_):
        xml_guardados.append(serie_numero)

    async def guardar_pdf_sunat(db, empresa_id, periodo, libro_pedido, serie_numero, ruta, bytes_):
        libros_pedidos.append(libro_pedido)
        punteros_pdf.append((serie_numero, ruta, bytes_))

    async def clasificar(db, documento, empresa) -> dict:
        clasificados.append(documento["serie_numero"])
        return {}

    async def obtener_detalles(
        empresa,
        comprobantes,
        libro=None,
        progreso=None,
        al_extraer=None,
        al_descargar=None,
        al_descargar_xml=None,
        al_extraer_leyenda=None,
        **resto,
    ):
        libros_pedidos.append(libro)
        assert resto.get("descargar_pdf") is True, "la extracción debe pedir también el PDF"

        # Igual que Playwright: el recorrido ocurre fuera del loop.
        def en_otro_hilo():
            hechos_ok = {}
            for hechos, comprobante in enumerate(comprobantes):
                serie = comprobante["serie_numero"]
                if progreso:
                    progreso(hechos, serie)
                if serie == corta_en:
                    # El portal se cae a media lista.
                    break
                hechos_ok[serie] = [{"descripcion": "un ítem"}]
                if al_extraer:
                    al_extraer(serie, hechos_ok[serie])
                if al_descargar_xml and serie.startswith("E"):
                    al_descargar_xml(serie, b"<Invoice/>")
                if al_descargar and serie not in sin_pdf:
                    al_descargar(serie, b"%PDF-1.4 " + serie.encode())
            return hechos_ok

        return await asyncio.to_thread(en_otro_hilo)

    repo = detalle_service.repo_comprobantes
    monkeypatch.setattr(repo, "listar_pendientes_sunat", listar_pendientes_sunat)
    monkeypatch.setattr(repo, "contar_pendientes_sunat", contar_pendientes_sunat)
    monkeypatch.setattr(repo, "guardar_detalle_sunat", guardar_detalle_sunat)
    monkeypatch.setattr(repo, "guardar_xml_sunat", guardar_xml_sunat)
    monkeypatch.setattr(repo, "guardar_pdf_sunat", guardar_pdf_sunat)
    monkeypatch.setattr(detalle_service.scraping_sunat, "obtener_detalles", obtener_detalles)

    async def principal():
        resultado = await detalle_service.extraer(None, EMPRESA, "202606", libro, reportar)
        # Los avisos del hilo se agendan sin esperarlos: se les da un turno de
        # loop para que se vacíen antes de mirar la lista.
        await asyncio.sleep(0)
        return resultado

    return {
        "resultado": asyncio.run(principal()),
        "reportes": reportes,
        "guardados": guardados,
        "libros": libros_pedidos,
        "xml": xml_guardados,
        "pdfs": punteros_pdf,
        "clasificados": clasificados,
    }


def test_reporta_el_avance_de_cada_comprobante(monkeypatch):
    salida = _correr(monkeypatch, PENDIENTES)

    assert salida["resultado"] == {
        "procesados": 3,
        "con_detalle": 3,
        "sin_detalle": 0,
        "descargados_pdf": 3,
        "sin_pdf": 0,
        "pendientes": 0,
    }

    reportes = salida["reportes"]
    # Uno por comprobante, además del inicial y el final.
    intermedios = [r for r in reportes if r[2].startswith("Extrayendo F001-")]
    assert [(actual, total) for actual, total, _ in intermedios] == [(0, 3), (1, 3), (2, 3)]
    assert intermedios[0][2] == "Extrayendo F001-1 (1 de 3)"

    assert reportes[0] == (0, 3, "Extrayendo detalle y PDF de 3 comprobantes")
    assert reportes[-1] == (3, 3, "Listo: 3 de 3 con detalle, 3 de 3 con PDF")


def test_sin_pendientes_no_abre_el_navegador(monkeypatch):
    salida = _correr(monkeypatch, [])

    assert salida["resultado"]["procesados"] == 0
    assert salida["resultado"]["descargados_pdf"] == 0
    assert salida["reportes"] == [(0, 0, "No hay comprobantes pendientes de detalle ni de PDF")]


def test_avisa_cuando_el_tope_recorta_el_trabajo(monkeypatch):
    # `listar_pendientes_sunat` corta en SUNAT_MAX_COMPROBANTES. Si el periodo
    # tiene más, el job debe decirlo: antes terminaba igual que si los hubiera
    # hecho todos y no había manera de saber que faltaba otra vuelta.
    salida = _correr(monkeypatch, PENDIENTES, total_en_bd=10)

    assert salida["resultado"]["pendientes"] == 7
    assert salida["reportes"][0] == (
        0,
        3,
        "Extrayendo 3 comprobantes; quedarán 7 para otra vuelta",
    )


def test_guarda_lo_ya_extraido_aunque_el_portal_se_caiga(monkeypatch):
    # El caso real: el portal dejó de responder en el tercer comprobante. Los
    # dos anteriores tienen que estar en la base, con detalle y con PDF.
    salida = _correr(monkeypatch, PENDIENTES, corta_en="F001-3")

    assert salida["guardados"] == ["F001-1", "F001-2"]
    assert [serie for serie, _, _ in salida["pdfs"]] == ["F001-1", "F001-2"]
    assert salida["resultado"]["con_detalle"] == 2
    assert salida["resultado"]["sin_detalle"] == 1
    assert salida["resultado"]["descargados_pdf"] == 2
    assert salida["resultado"]["sin_pdf"] == 1


def test_no_guarda_dos_veces_el_mismo_comprobante(monkeypatch):
    # El repaso final es una red de seguridad, no una segunda escritura.
    salida = _correr(monkeypatch, PENDIENTES)

    assert salida["guardados"] == ["F001-1", "F001-2", "F001-3"]


def test_el_libro_llega_al_repositorio_y_al_scraper(monkeypatch):
    # Sin el libro, una extracción de ventas recogería comprobantes de compras
    # y el detalle acabaría escrito en el documento equivocado: `serie_numero`
    # no es único dentro de un periodo.
    salida = _correr(monkeypatch, PENDIENTES, libro=Libro.VENTAS)

    assert salida["libros"]
    assert set(salida["libros"]) == {Libro.VENTAS}


def test_guarda_el_pdf_en_disco_y_su_puntero_en_la_base(monkeypatch, almacen):
    # El PDF viaja en la misma pasada que el detalle: antes hacía falta un
    # segundo trabajo (y una segunda visita al portal) para tenerlo.
    salida = _correr(monkeypatch, PENDIENTES)

    rutas = {serie: ruta for serie, ruta, _ in salida["pdfs"]}
    assert rutas["F001-1"] == "20608997106/compras/2026/06/facturas/F001-1.pdf"
    for ruta in rutas.values():
        assert (almacen / ruta).read_bytes().startswith(b"%PDF")


def test_un_comprobante_sin_pdf_no_pierde_su_detalle(monkeypatch):
    # El portal no siempre entrega el documento. Quedarse sin respaldo no
    # puede costar el detalle ni la clasificación de ese comprobante.
    salida = _correr(monkeypatch, PENDIENTES, sin_pdf={"F001-2"})

    assert salida["guardados"] == ["F001-1", "F001-2", "F001-3"]
    assert [serie for serie, _, _ in salida["pdfs"]] == ["F001-1", "F001-3"]
    assert salida["resultado"]["con_detalle"] == 3
    assert salida["resultado"]["descargados_pdf"] == 2
    assert salida["resultado"]["sin_pdf"] == 1


def test_respeta_lo_que_el_comprobante_ya_tenia(monkeypatch):
    # Uno entró a la lista sólo porque le faltaba el PDF (ya tenía detalle) y
    # otro sólo porque le faltaba el detalle (ya tenía PDF). Ni el detalle ni
    # el PDF previos se reescriben, pero los dos cuentan como cubiertos.
    pendientes = [
        {
            "_id": "1",
            "serie_numero": "F001-1",
            "serie": "F001",
            "numero": "1",
            "tipo_cp": "01",
            "detalle_sunat": [{"descripcion": "ya estaba"}],
        },
        {
            "_id": "2",
            "serie_numero": "F001-2",
            "serie": "F001",
            "numero": "2",
            "tipo_cp": "01",
            "pdf_sunat": {"ruta": "x.pdf", "bytes": 1},
        },
    ]
    salida = _correr(monkeypatch, pendientes)

    assert salida["guardados"] == ["F001-2"]
    assert [serie for serie, _, _ in salida["pdfs"]] == ["F001-1"]
    assert salida["resultado"]["con_detalle"] == 2
    assert salida["resultado"]["descargados_pdf"] == 1
    assert salida["resultado"]["sin_pdf"] == 0
    assert salida["clasificados"] == []


def test_guarda_el_xml_si_el_scraper_lo_entrega(monkeypatch):
    pendientes_con_sol = [
        {
            "_id": "1",
            "serie_numero": "E001-1929",
            "serie": "E001",
            "numero": "1929",
            "tipo_cp": "01",
        },
        {"_id": "2", "serie_numero": "F001-2", "serie": "F001", "numero": "2", "tipo_cp": "01"},
    ]
    salida = _correr(monkeypatch, pendientes_con_sol)

    assert "E001-1929" in salida["guardados"]
    assert "F001-2" in salida["guardados"]
    assert salida["xml"] == ["E001-1929"]
