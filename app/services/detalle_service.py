from __future__ import annotations

import asyncio
import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.repositories import comprobantes as repo_comprobantes
from app.services import rag_service, scraping_sunat
from app.services.jobs_service import Reportador

logger = logging.getLogger(__name__)


async def extraer(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    reportar: Reportador,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    pendientes = await repo_comprobantes.listar_sin_detalle(db, empresa_id, periodo)

    if not pendientes:
        await reportar(0, 0, "No hay comprobantes pendientes de detalle")
        return {"procesados": 0, "con_detalle": 0}

    total = len(pendientes)

    # El listado corta en `SUNAT_MAX_COMPROBANTES`. Decirlo aquí evita que un
    # periodo grande parezca terminado cuando sólo se hizo la primera tanda.
    faltan = await repo_comprobantes.contar_sin_detalle(db, empresa_id, periodo) - total
    if faltan > 0:
        await reportar(
            0, total, f"Extrayendo {total} comprobantes; quedarán {faltan} para otra vuelta"
        )
    else:
        await reportar(0, total, f"Extrayendo detalle de {total} comprobantes")

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
            futuro = asyncio.run_coroutine_threadsafe(
                reportar(hechos, total, mensaje), loop
            )
        except RuntimeError:
            # El loop se cerró: el scraping sigue, pero
            # ya no hay a quién informarle.
            logger.debug("No se pudo reportar el avance: el loop está cerrado")
            return
        futuro.add_done_callback(_registrar_fallo)

    # Guardar sobre la marcha, no al final: si el portal se cae a mitad de la
    # lista, lo ya recorrido queda en la base en vez de perderse con el resto.
    guardados: set[str] = set()

    def guardar(serie_numero: str, detalle: list) -> None:
        if not detalle:
            return
        try:
            futuro = asyncio.run_coroutine_threadsafe(
                repo_comprobantes.guardar_detalle_sunat(
                    db, empresa_id, periodo, serie_numero, detalle
                ),
                loop,
            )
        except RuntimeError:
            logger.debug("No se pudo guardar el detalle: el loop está cerrado")
            return
        guardados.add(serie_numero)
        futuro.add_done_callback(_registrar_fallo)

    resultados = await scraping_sunat.obtener_detalles(
        empresa, pendientes, progreso=avisar, al_extraer=guardar
    )

    # Red de seguridad por si algún aviso se perdió: reintenta sólo lo que no
    # se llegó a agendar.
    con_detalle = len(guardados)
    for serie_numero, detalle in resultados.items():
        if not detalle or serie_numero in guardados:
            continue
        await repo_comprobantes.guardar_detalle_sunat(
            db, empresa_id, periodo, serie_numero, detalle
        )
        con_detalle += 1

    # El detalle extraído es la glosa de entrada del RAG. Cada comprobante se
    # aísla: una caída temporal de Render no borra el scraping ni impide que los
    # demás comprobantes terminen.
    limite = asyncio.Semaphore(settings.RAG_API_MAX_CONCURRENCY)
    enriquecidos = 0
    errores_rag = 0

    async def enriquecer(documento: dict[str, Any]) -> None:
        nonlocal enriquecidos, errores_rag
        serie_numero = documento.get("serie_numero", "")
        detalle = resultados.get(serie_numero) or []
        if not detalle:
            return
        try:
            async with limite:
                rag = await rag_service.enriquecer(documento, detalle, empresa)
            metadata = dict(documento.get("metadata_procesada") or {})
            metadata["rag"] = rag
            await repo_comprobantes.guardar_metadata(db, documento["_id"], metadata)
            enriquecidos += 1
        except Exception:
            errores_rag += 1
            logger.exception("Error enriqueciendo con RAG serie_numero=%s", serie_numero)

    if resultados:
        await reportar(total, total, "Clasificando códigos contables con RAG")
        await asyncio.gather(*(enriquecer(documento) for documento in pendientes))

    sin_detalle = total - con_detalle

    await reportar(total, total, "Extracción y clasificación RAG finalizadas")
    logger.info(
        "Detalle extraído ruc=%s periodo=%s procesados=%s con_detalle=%s sin_detalle=%s faltan=%s",
        empresa.get("ruc"),
        periodo,
        total,
        con_detalle,
        sin_detalle,
        max(faltan, 0),
    )
    return {
        "procesados": total,
        "con_detalle": con_detalle,
        "sin_detalle": sin_detalle,
        "pendientes": max(faltan, 0),
        "enriquecidos_rag": enriquecidos,
        "errores_rag": errores_rag,
    }
