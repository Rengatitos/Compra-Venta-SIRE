from __future__ import annotations

import asyncio
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.services import almacen_pdf, scraping_sunat
from app.services.jobs_service import Reportador

logger = logging.getLogger(__name__)


async def extraer(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    libro: Libro,
    reportar: Reportador,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    ruc = empresa["ruc"]

    # Una sola visita al portal por comprobante: se lleva el detalle de ítems
    # **y** el PDF. Entra en la lista todo lo que le falte cualquiera de las
    # dos cosas; lo que ya tenga se respeta y no se vuelve a escribir.
    pendientes = await repo_comprobantes.listar_pendientes_sunat(db, empresa_id, periodo, libro)

    if not pendientes:
        await reportar(0, 0, "No hay comprobantes pendientes de detalle ni de PDF")
        return {
            "procesados": 0,
            "con_detalle": 0,
            "sin_detalle": 0,
            "descargados_pdf": 0,
            "sin_pdf": 0,
            "pendientes": 0,
        }

    total = len(pendientes)

    # El listado corta en `SUNAT_MAX_COMPROBANTES`. Decirlo aquí evita que un
    # periodo grande parezca terminado cuando sólo se hizo la primera tanda.
    faltan = (
        await repo_comprobantes.contar_pendientes_sunat(db, empresa_id, periodo, libro) - total
    )
    if faltan > 0:
        await reportar(
            0, total, f"Extrayendo {total} comprobantes; quedarán {faltan} para otra vuelta"
        )
    else:
        await reportar(0, total, f"Extrayendo detalle y PDF de {total} comprobantes")

    # El scraping corre en un hilo aparte (Playwright es síncrono) y avisa desde
    # ahí. Motor está atado al loop, así que el reporte tiene que volver a él;
    # no se espera el resultado para no bloquear el navegador contra Mongo.
    loop = asyncio.get_running_loop()

    def _registrar_fallo(futuro) -> None:
        if futuro.exception():
            logger.warning("No se pudo guardar el avance: %s", futuro.exception())

    def avisar(hechos: int, serie_numero: str) -> None:
        mensaje = f"Extrayendo {serie_numero} ({hechos + 1} de {total})"
        try:
            futuro = asyncio.run_coroutine_threadsafe(reportar(hechos, total, mensaje), loop)
        except RuntimeError:
            # El loop se cerró: el scraping sigue, pero
            # ya no hay a quién informarle.
            logger.debug("No se pudo reportar el avance: el loop está cerrado")
            return
        futuro.add_done_callback(_registrar_fallo)

    # Guardar sobre la marcha, no al final: si el portal se cae a mitad de la
    # lista, lo ya recorrido queda en la base en vez de perderse con el resto.
    guardados: set[str] = set()
    por_serie = {doc.get("serie_numero", ""): doc for doc in pendientes}
    # Los que entraron sólo por el PDF ya tienen detalle: se cuenta como
    # hecho y no se reescribe.
    con_detalle_previo = {
        serie for serie, doc in por_serie.items() if doc.get("detalle_sunat") is not None
    }
    con_pdf_previo = {
        serie for serie, doc in por_serie.items() if doc.get("pdf_sunat") is not None
    }
    pdfs_guardados: dict[str, int] = {}

    def guardar(serie_numero: str, detalle: list) -> None:
        if not detalle or serie_numero in con_detalle_previo:
            return
        try:
            futuro = asyncio.run_coroutine_threadsafe(
                repo_comprobantes.guardar_detalle_sunat(
                    db, empresa_id, periodo, libro, serie_numero, detalle
                ),
                loop,
            )
        except RuntimeError:
            logger.debug("No se pudo guardar el detalle: el loop está cerrado")
            return
        guardados.add(serie_numero)
        futuro.add_done_callback(_registrar_fallo)

    def guardar_leyenda(serie_numero: str, leyenda: list) -> None:
        if not leyenda:
            return
        try:
            futuro = asyncio.run_coroutine_threadsafe(
                repo_comprobantes.guardar_leyenda_sunat(
                    db, empresa_id, periodo, libro, serie_numero, leyenda
                ),
                loop,
            )
        except RuntimeError:
            logger.debug("No se pudo guardar la leyenda: el loop está cerrado")
            return
        futuro.add_done_callback(_registrar_fallo)

    def guardar_pdf(serie_numero: str, contenido: bytes) -> None:
        doc = por_serie.get(serie_numero)
        if doc is None or not contenido or serie_numero in con_pdf_previo:
            return

        # Mismo reparto que `pdf_service`: el archivo se escribe aquí, en el
        # hilo del scraper (I/O de disco, no toca el loop); a Mongo sólo va el
        # puntero, y ese sí vuelve al loop.
        try:
            destino = almacen_pdf.guardar(
                ruc,
                libro,
                periodo,
                doc.get("tipo_cp"),
                doc.get("serie", ""),
                doc.get("numero", ""),
                contenido,
            )
        except (OSError, ValueError):
            logger.exception("No se pudo guardar el PDF serie_numero=%s", serie_numero)
            return

        try:
            futuro = asyncio.run_coroutine_threadsafe(
                repo_comprobantes.guardar_pdf_sunat(
                    db,
                    empresa_id,
                    periodo,
                    libro,
                    serie_numero,
                    almacen_pdf.relativa(destino),
                    len(contenido),
                ),
                loop,
            )
        except RuntimeError:
            logger.debug("No se pudo guardar el puntero del PDF: el loop está cerrado")
            return
        pdfs_guardados[serie_numero] = len(contenido)
        futuro.add_done_callback(_registrar_fallo)

    def guardar_xml(serie_numero: str, contenido_xml: bytes) -> None:
        doc = por_serie.get(serie_numero)
        if doc is None or not contenido_xml:
            return
        try:
            destino = almacen_pdf.guardar(
                empresa["ruc"],
                libro,
                periodo,
                doc.get("tipo_cp"),
                doc.get("serie", ""),
                doc.get("numero", ""),
                contenido_xml,
                extension="xml",
                subcarpeta="xml",
            )
        except (OSError, ValueError):
            logger.exception("No se pudo guardar el XML serie_numero=%s", serie_numero)
            return

        try:
            futuro = asyncio.run_coroutine_threadsafe(
                repo_comprobantes.guardar_xml_sunat(
                    db,
                    empresa_id,
                    periodo,
                    libro,
                    serie_numero,
                    almacen_pdf.relativa(destino),
                    len(contenido_xml),
                ),
                loop,
            )
        except RuntimeError:
            logger.debug("No se pudo guardar el puntero del XML: el loop está cerrado")
            return
        futuro.add_done_callback(_registrar_fallo)

    resultados = await scraping_sunat.obtener_detalles(
        empresa,
        pendientes,
        libro=libro,
        progreso=avisar,
        al_extraer=guardar,
        descargar_pdf=True,
        al_descargar=guardar_pdf,
        al_descargar_xml=guardar_xml,
        al_extraer_leyenda=guardar_leyenda,
    )

    # Red de seguridad por si algún aviso se perdió: reintenta sólo lo que no
    # se llegó a agendar.
    con_detalle = len(guardados)
    for serie_numero, detalle in resultados.items():
        if not detalle or serie_numero in guardados or serie_numero in con_detalle_previo:
            continue
        await repo_comprobantes.guardar_detalle_sunat(
            db, empresa_id, periodo, libro, serie_numero, detalle
        )
        con_detalle += 1
    con_detalle += len(con_detalle_previo)
    con_pdf = len(pdfs_guardados) + len(con_pdf_previo)

    sin_detalle = total - con_detalle
    sin_pdf = total - con_pdf

    await reportar(
        total,
        total,
        f"Listo: {con_detalle} de {total} con detalle, {con_pdf} de {total} con PDF",
    )
    logger.info(
        "Detalle extraído ruc=%s periodo=%s libro=%s "
        "procesados=%s con_detalle=%s sin_detalle=%s pdfs=%s sin_pdf=%s faltan=%s",
        empresa.get("ruc"),
        periodo,
        libro.value,
        total,
        con_detalle,
        sin_detalle,
        len(pdfs_guardados),
        sin_pdf,
        max(faltan, 0),
    )
    return {
        "procesados": total,
        "con_detalle": con_detalle,
        "sin_detalle": sin_detalle,
        "descargados_pdf": len(pdfs_guardados),
        "sin_pdf": sin_pdf,
        "pendientes": max(faltan, 0),
    }
