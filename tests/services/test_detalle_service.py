"""El avance de la extracción nace en el hilo de Playwright y tiene que llegar
al job, que vive en el loop. Es el punto donde antes se perdía: el trabajo se
pasaba minutos en `0 / N` y no había forma de distinguirlo de uno colgado."""

from __future__ import annotations

import asyncio

from app.domain.comprobante import Libro
from app.services import detalle_service

EMPRESA = {"_id": "abc123", "ruc": "20608997106"}
PENDIENTES = [
    {"_id": "1", "serie_numero": "F001-1", "tipo_cp": "01", "tipo_doc_identidad": "6"},
    {"_id": "2", "serie_numero": "F001-2", "tipo_cp": "01", "tipo_doc_identidad": "6"},
    {"_id": "3", "serie_numero": "F001-3", "tipo_cp": "01", "tipo_doc_identidad": "6"},
]


def _correr(monkeypatch, pendientes, total_en_bd=None, corta_en=None, libro=Libro.COMPRAS):
    """Ejecuta `extraer` con el repositorio y el scraping simulados."""
    reportes: list[tuple[int, int, str]] = []
    guardados: list[str] = []
    libros_pedidos: list[Libro] = []

    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        reportes.append((actual, total, mensaje))

    async def listar_sin_detalle(db, empresa_id, periodo, libro_pedido):
        libros_pedidos.append(libro_pedido)
        return pendientes

    async def contar_sin_detalle(db, empresa_id, periodo, libro_pedido):
        return len(pendientes) if total_en_bd is None else total_en_bd

    async def guardar_detalle_sunat(db, empresa_id, periodo, libro_pedido, serie_numero, detalle):
        libros_pedidos.append(libro_pedido)
        guardados.append(serie_numero)

    async def obtener_detalles(
        empresa, comprobantes, libro=None, progreso=None, al_extraer=None, **resto
    ):
        libros_pedidos.append(libro)
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
            return hechos_ok

        return await asyncio.to_thread(en_otro_hilo)

    monkeypatch.setattr(
        detalle_service.repo_comprobantes, "listar_sin_detalle", listar_sin_detalle
    )
    monkeypatch.setattr(
        detalle_service.repo_comprobantes, "contar_sin_detalle", contar_sin_detalle
    )
    monkeypatch.setattr(
        detalle_service.repo_comprobantes, "guardar_detalle_sunat", guardar_detalle_sunat
    )
    async def guardar_metadata(db, documento_id, metadata) -> None:
        return None

    async def clasificar(db, documento, empresa) -> dict:
        return {}

    monkeypatch.setattr(detalle_service.repo_comprobantes, "guardar_metadata", guardar_metadata)
    monkeypatch.setattr(detalle_service.scraping_sunat, "obtener_detalles", obtener_detalles)
    monkeypatch.setattr(detalle_service.ollama_rag, "clasificar", clasificar)

    async def principal():
        resultado = await detalle_service.extraer(None, EMPRESA, "202606", libro, reportar)
        # Los avisos del hilo se agendan sin esperarlos: se les da un turno de
        # loop para que se vacíen antes de mirar la lista.
        await asyncio.sleep(0)
        return resultado

    return asyncio.run(principal()), reportes, guardados, libros_pedidos


def test_reporta_el_avance_de_cada_comprobante(monkeypatch):
    resultado, reportes, guardados, _ = _correr(monkeypatch, PENDIENTES)

    assert resultado == {
        "procesados": 3,
        "con_detalle": 3,
        "sin_detalle": 0,
        "pendientes": 0,
        "enriquecidos_rag": 3,
        "errores_rag": 0,
    }

    # Uno por comprobante, además del inicial y el final.
    intermedios = [r for r in reportes if r[2].startswith("Extrayendo F001-")]
    assert [(actual, total) for actual, total, _ in intermedios] == [(0, 3), (1, 3), (2, 3)]
    assert intermedios[0][2] == "Extrayendo F001-1 (1 de 3)"

    assert reportes[0] == (0, 3, "Extrayendo detalle de 3 comprobantes")
    assert reportes[-1] == (3, 3, "Extracción y clasificación RAG finalizadas")


def test_sin_pendientes_no_abre_el_navegador(monkeypatch):
    resultado, reportes, guardados, _ = _correr(monkeypatch, [])

    assert resultado == {"procesados": 0, "con_detalle": 0}
    assert reportes == [(0, 0, "No hay comprobantes pendientes de detalle")]


def test_avisa_cuando_el_tope_recorta_el_trabajo(monkeypatch):
    # `listar_sin_detalle` corta en SUNAT_MAX_COMPROBANTES. Si el periodo tiene
    # más, el job debe decirlo: antes terminaba igual que si los hubiera hecho
    # todos y no había manera de saber que faltaba otra vuelta.
    resultado, reportes, guardados, _ = _correr(monkeypatch, PENDIENTES, total_en_bd=10)

    assert resultado["pendientes"] == 7
    assert resultado["enriquecidos_rag"] == 3
    assert reportes[0] == (0, 3, "Extrayendo 3 comprobantes; quedarán 7 para otra vuelta")


def test_guarda_lo_ya_extraido_aunque_el_portal_se_caiga(monkeypatch):
    # El caso real: el portal dejó de responder en el tercer comprobante. Los
    # dos anteriores tienen que estar en la base. Antes el guardado ocurría al
    # final, así que un tropiezo se llevaba por delante todo lo ya recorrido.
    resultado, _, guardados, _libros = _correr(monkeypatch, PENDIENTES, corta_en="F001-3")

    assert guardados == ["F001-1", "F001-2"]
    assert resultado["con_detalle"] == 2
    assert resultado["sin_detalle"] == 1


def test_no_guarda_dos_veces_el_mismo_comprobante(monkeypatch):
    # El repaso final es una red de seguridad, no una segunda escritura.
    _, _, guardados, _libros = _correr(monkeypatch, PENDIENTES)

    assert guardados == ["F001-1", "F001-2", "F001-3"]


def test_el_libro_llega_al_repositorio_y_al_scraper(monkeypatch):
    # Sin el libro, una extracción de ventas recogería comprobantes de compras
    # y el detalle acabaría escrito en el documento equivocado: `serie_numero`
    # no es único dentro de un periodo.
    _, _, _, libros = _correr(monkeypatch, PENDIENTES, libro=Libro.VENTAS)

    assert libros
    assert set(libros) == {Libro.VENTAS}
