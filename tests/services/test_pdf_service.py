"""Los PDFs llegan desde el hilo de Playwright y hay que guardarlos sobre la
marcha: si el portal se cae a mitad de la lista, lo ya descargado tiene que
quedar en disco y con su puntero en la base."""

from __future__ import annotations

import asyncio

import pytest

from app.domain.comprobante import Libro
from app.services import almacen_pdf, pdf_service

EMPRESA = {"_id": "abc123", "ruc": "20608997106"}
PENDIENTES = [
    {"_id": "1", "serie_numero": "F001-1", "tipo_cp": "01", "serie": "F001", "numero": "1"},
    {"_id": "2", "serie_numero": "B001-2", "tipo_cp": "03", "serie": "B001", "numero": "2"},
    {"_id": "3", "serie_numero": "F001-3", "tipo_cp": "01", "serie": "F001", "numero": "3"},
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
    """Ejecuta `descargar` con el repositorio y el scraping simulados."""
    reportes: list[tuple[int, int, str]] = []
    punteros: list[tuple[str, str, int]] = []
    libros_pedidos: list[Libro] = []

    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        reportes.append((actual, total, mensaje))

    async def listar_sin_pdf(db, empresa_id, periodo, libro_pedido):
        libros_pedidos.append(libro_pedido)
        return pendientes

    async def contar_sin_pdf(db, empresa_id, periodo, libro_pedido):
        return len(pendientes) if total_en_bd is None else total_en_bd

    async def guardar_pdf_sunat(
        db, empresa_id, periodo, libro_pedido, serie_numero, ruta, bytes_
    ):
        libros_pedidos.append(libro_pedido)
        punteros.append((serie_numero, ruta, bytes_))

    async def obtener_detalles(
        empresa, comprobantes, libro=None, progreso=None, al_descargar=None, **resto
    ):
        libros_pedidos.append(libro)
        assert resto.get("descargar_pdf") is True, "el scraper debe recibir la orden de PDF"

        # Igual que Playwright: el recorrido ocurre fuera del loop.
        def en_otro_hilo():
            for hechos, comprobante in enumerate(comprobantes):
                serie = comprobante["serie_numero"]
                if progreso:
                    progreso(hechos, serie)
                if serie == corta_en:
                    break
                if serie in sin_pdf:
                    # El portal no dio el documento: el scraper no llama al
                    # callback y el comprobante se queda sin respaldo.
                    continue
                if al_descargar:
                    al_descargar(serie, b"%PDF-1.4 " + serie.encode())
            return {}

        return await asyncio.to_thread(en_otro_hilo)

    monkeypatch.setattr(pdf_service.repo_comprobantes, "listar_sin_pdf", listar_sin_pdf)
    monkeypatch.setattr(pdf_service.repo_comprobantes, "contar_sin_pdf", contar_sin_pdf)
    monkeypatch.setattr(pdf_service.repo_comprobantes, "guardar_pdf_sunat", guardar_pdf_sunat)
    monkeypatch.setattr(pdf_service.scraping_sunat, "obtener_detalles", obtener_detalles)

    async def principal():
        resultado = await pdf_service.descargar(None, EMPRESA, "202606", libro, reportar)
        # Los punteros se agendan sin esperarlos: se les da un turno de loop
        # para que se vacíen antes de mirar la lista.
        await asyncio.sleep(0)
        return resultado

    return asyncio.run(principal()), reportes, punteros, libros_pedidos


def test_guarda_el_pdf_en_disco_y_su_puntero_en_la_base(monkeypatch, almacen):
    resultado, _, punteros, _ = _correr(monkeypatch, PENDIENTES)

    assert resultado == {
        "procesados": 3,
        "descargados": 3,
        "sin_pdf": 0,
        "pendientes": 0,
        "bytes": sum(len(b"%PDF-1.4 " + f["serie_numero"].encode()) for f in PENDIENTES),
    }

    # El puntero es relativo, y el archivo está donde dice.
    rutas = {serie: ruta for serie, ruta, _ in punteros}
    assert rutas["F001-1"] == "20608997106/compras/2026/06/facturas/F001-1.pdf"
    assert rutas["B001-2"] == "20608997106/compras/2026/06/boletas/B001-2.pdf"
    for ruta in rutas.values():
        assert (almacen / ruta).read_bytes().startswith(b"%PDF")


def test_sin_pendientes_no_abre_el_navegador(monkeypatch):
    resultado, reportes, punteros, _ = _correr(monkeypatch, [])

    assert resultado["procesados"] == 0
    assert punteros == []
    assert reportes == [(0, 0, "No hay comprobantes pendientes de PDF")]


def test_reporta_el_avance_de_cada_comprobante(monkeypatch):
    _, reportes, _, _ = _correr(monkeypatch, PENDIENTES)

    intermedios = [r for r in reportes if r[2].endswith(" de 3)")]
    assert [(actual, total) for actual, total, _ in intermedios] == [(0, 3), (1, 3), (2, 3)]
    assert intermedios[0][2] == "Descargando F001-1 (1 de 3)"
    assert reportes[-1] == (3, 3, "Descarga terminada: 3 de 3 con PDF")


def test_avisa_cuando_el_tope_recorta_el_trabajo(monkeypatch):
    # `listar_sin_pdf` corta en SUNAT_MAX_PDFS. Si el periodo tiene más, el
    # trabajo debe decirlo en vez de terminar como si los hubiera hecho todos.
    resultado, reportes, _, _ = _correr(monkeypatch, PENDIENTES, total_en_bd=10)

    assert resultado["pendientes"] == 7
    assert reportes[0] == (0, 3, "Descargando 3 PDFs; quedarán 7 para otra vuelta")


def test_guarda_lo_ya_descargado_aunque_el_portal_se_caiga(monkeypatch, almacen):
    resultado, _, punteros, _ = _correr(monkeypatch, PENDIENTES, corta_en="F001-3")

    assert [serie for serie, _, _ in punteros] == ["F001-1", "B001-2"]
    assert resultado["descargados"] == 2
    assert resultado["sin_pdf"] == 1


def test_un_comprobante_sin_pdf_no_tumba_el_lote(monkeypatch):
    # El portal no entrega el documento de forma consistente. Perder un
    # respaldo no puede costar los otros dos.
    resultado, _, punteros, _ = _correr(monkeypatch, PENDIENTES, sin_pdf={"B001-2"})

    assert [serie for serie, _, _ in punteros] == ["F001-1", "F001-3"]
    assert resultado == {
        "procesados": 3,
        "descargados": 2,
        "sin_pdf": 1,
        "pendientes": 0,
        "bytes": len(b"%PDF-1.4 F001-1") + len(b"%PDF-1.4 F001-3"),
    }


def test_una_ruta_imposible_no_tumba_el_lote(monkeypatch):
    # Una serie sin nada utilizable hace fallar `almacen_pdf.guardar`. Es un
    # comprobante perdido, no un trabajo perdido.
    pendientes = [
        {"_id": "1", "serie_numero": "///-1", "tipo_cp": "01", "serie": "///", "numero": "1"},
        *PENDIENTES[:1],
    ]
    resultado, _, punteros, _ = _correr(monkeypatch, pendientes)

    assert [serie for serie, _, _ in punteros] == ["F001-1"]
    assert resultado["descargados"] == 1
    assert resultado["sin_pdf"] == 1


def test_el_libro_llega_al_repositorio_y_al_scraper(monkeypatch):
    # Sin el libro, la descarga de ventas buscaría en la bandeja de compras y
    # el puntero acabaría en el documento equivocado: `serie_numero` no es
    # único dentro de un periodo.
    _, _, _, libros = _correr(monkeypatch, PENDIENTES, libro=Libro.VENTAS)

    assert libros
    assert set(libros) == {Libro.VENTAS}
