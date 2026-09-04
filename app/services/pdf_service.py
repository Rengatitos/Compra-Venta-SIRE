"""Descarga de los PDFs de los comprobantes desde el portal SOL.

Mismo esqueleto que `detalle_service`: el scraping corre en un hilo aparte
—Playwright es síncrono—, avisa desde ahí, y cada PDF se guarda en cuanto está
en vez de al terminar el lote. Lo que cambia es qué se persiste: aquí el
contenido va a disco (`almacen_pdf`) y a Mongo sólo el puntero.
"""

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


async def descargar(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    libro: Libro,
    reportar: Reportador,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    ruc = empresa["ruc"]

    pendientes = await repo_comprobantes.listar_sin_pdf(db, empresa_id, periodo, libro)

    if not pendientes:
        await reportar(0, 0, "No hay comprobantes pendientes de PDF")
        return {"procesados": 0, "descargados": 0, "sin_pdf": 0, "pendientes": 0, "bytes": 0}

    total = len(pendientes)

    # `listar_sin_pdf` corta en `SUNAT_MAX_PDFS`. Sin este aviso, un periodo
    # con más comprobantes que el tope terminaría el trabajo como si los
    # hubiera cubierto todos.
    faltan = await repo_comprobantes.contar_sin_pdf(db, empresa_id, periodo, libro) - total
    if faltan > 0:
        await reportar(
            0, total, f"Descargando {total} PDFs; quedarán {faltan} para otra vuelta"
        )
    else:
        await reportar(0, total, f"Descargando el PDF de {total} comprobantes")

    # Los callbacks se ejecutan en el hilo de Playwright y Motor está atado al
    # loop, así que el trabajo contra Mongo tiene que volver a él. No se espera
    # el resultado para no bloquear el navegador.
    loop = asyncio.get_running_loop()
    por_serie = {doc.get("serie_numero", ""): doc for doc in pendientes}
    guardados: dict[str, int] = {}

    def _registrar_fallo(futuro) -> None:
        if futuro.exception():
            logger.warning("No se pudo guardar el avance: %s", futuro.exception())

    def avisar(hechos: int, serie_numero: str) -> None:
        mensaje = f"Descargando {serie_numero} ({hechos + 1} de {total})"
        try:
            futuro = asyncio.run_coroutine_threadsafe(reportar(hechos, total, mensaje), loop)
        except RuntimeError:
            logger.debug("No se pudo reportar el avance: el loop está cerrado")
            return
        futuro.add_done_callback(_registrar_fallo)

    def guardar(serie_numero: str, contenido: bytes) -> None:
        documento = por_serie.get(serie_numero)
        if documento is None or not contenido:
            return

        # El archivo se escribe en el hilo del scraper: es I/O de disco local,
        # no toca el loop, y hacerlo aquí evita retener los bytes en memoria
        # esperando turno. Lo que sí vuelve al loop es el puntero en Mongo.
        try:
            destino = almacen_pdf.guardar(
                ruc,
                libro,
                periodo,
                documento.get("tipo_cp"),
                documento.get("serie", ""),
                documento.get("numero", ""),
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
        guardados[serie_numero] = len(contenido)
        futuro.add_done_callback(_registrar_fallo)

    await scraping_sunat.obtener_detalles(
        empresa,
        pendientes,
        libro=libro,
        progreso=avisar,
        descargar_pdf=True,
        al_descargar=guardar,
    )

    descargados = len(guardados)
    sin_pdf = total - descargados
    await reportar(total, total, f"Descarga terminada: {descargados} de {total} con PDF")
    logger.info(
        "Descarga de PDFs ruc=%s periodo=%s libro=%s descargados=%s sin_pdf=%s",
        ruc,
        periodo,
        libro.value,
        descargados,
        sin_pdf,
    )
    return {
        "procesados": total,
        "descargados": descargados,
        "sin_pdf": sin_pdf,
        "pendientes": max(faltan, 0),
        "bytes": sum(guardados.values()),
    }
