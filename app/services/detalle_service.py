from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories import comprobantes as repo_comprobantes
from app.services import scraping_sunat
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
    await reportar(0, total, f"Extrayendo detalle de {total} comprobantes")

    resultados = await scraping_sunat.obtener_detalles(empresa, pendientes)

    con_detalle = 0
    for serie_numero, detalle in resultados.items():
        if not detalle:
            continue
        await repo_comprobantes.guardar_detalle_sunat(
            db, empresa_id, periodo, serie_numero, detalle
        )
        con_detalle += 1

    await reportar(total, total, "Extracción finalizada")
    logger.info(
        "Detalle extraído ruc=%s periodo=%s procesados=%s con_detalle=%s",
        empresa.get("ruc"),
        periodo,
        total,
        con_detalle,
    )
    return {"procesados": total, "con_detalle": con_detalle}
