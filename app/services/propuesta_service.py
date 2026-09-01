from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.services.sunat import propuesta as api_propuesta

logger = logging.getLogger(__name__)


async def sincronizar(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    libro: Libro,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    registros = await api_propuesta.descargar(db, empresa, periodo, libro)

    if registros is None:
        await repo_periodos.actualizar_estado(db, empresa_id, periodo, "sin_propuesta")
        return {
            "nuevos": 0,
            "actualizados": 0,
            "descartados": 0,
            "mensaje": "SUNAT no tiene propuesta para el periodo indicado",
        }

    nuevos = 0
    actualizados = 0
    descartados = 0

    for registro in registros:
        comprobante = api_propuesta.a_comprobante(registro, libro)

        # Ya no se filtra por serie: el registro de ventas es en su mayoría
        # boletas (B, EB) y descartarlas dejaba fuera el grueso del libro. Se
        # guardan todos los comprobantes; sólo caen los que no se pueden
        # identificar y los de periodos vecinos.
        if not comprobante.es_valido:
            descartados += 1
            continue
        if not api_propuesta.pertenece_al_periodo(comprobante, periodo):
            descartados += 1
            continue

        if await repo_comprobantes.upsert(db, empresa_id, periodo, comprobante):
            nuevos += 1
        else:
            actualizados += 1

    await repo_periodos.actualizar_estado(db, empresa_id, periodo, "sincronizado")

    logger.info(
        "Propuesta sincronizada ruc=%s periodo=%s libro=%s "
        "nuevos=%s actualizados=%s descartados=%s",
        empresa.get("ruc"),
        periodo,
        libro.value,
        nuevos,
        actualizados,
        descartados,
    )

    return {
        "nuevos": nuevos,
        "actualizados": actualizados,
        "descartados": descartados,
        "mensaje": f"Se sincronizaron {nuevos + actualizados} comprobantes",
    }
