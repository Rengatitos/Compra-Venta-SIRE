"""Caché de fichas RUC de SUNAT (`app/services/sunat/ficha_ruc.py`).

Guarda la de cualquier contribuyente, registrado o no: las de las contrapartes
son las que más se consultan, porque cada proveedor aparece en muchos
comprobantes y la Consulta RUC cuesta segundos de navegador.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.repositories._mongo import NOMBRE_COL_FICHAS_RUC
from app.services.sunat.ficha_ruc import FichaRuc


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_FICHAS_RUC]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    await _col(db).create_index("ruc", unique=True)


def _vigente(documento: dict[str, Any]) -> bool:
    consultado = documento.get("consultado_en")
    if not isinstance(consultado, datetime):
        return False
    if consultado.tzinfo is None:
        consultado = consultado.replace(tzinfo=UTC)
    return datetime.now(UTC) - consultado < timedelta(days=settings.FICHA_RUC_VIGENCIA_DIAS)


async def obtener(db: AsyncIOMotorDatabase, ruc: str, solo_vigente: bool = True) -> FichaRuc | None:
    documento = await _col(db).find_one({"ruc": ruc}, {"_id": 0})
    if documento is None or (solo_vigente and not _vigente(documento)):
        return None
    return FichaRuc.model_validate(documento)


async def obtener_varias(db: AsyncIOMotorDatabase, rucs: list[str]) -> dict[str, FichaRuc]:
    """Las fichas vigentes de esos RUC, por RUC. Los que faltan no aparecen."""
    if not rucs:
        return {}
    salida: dict[str, FichaRuc] = {}
    async for documento in _col(db).find({"ruc": {"$in": rucs}}, {"_id": 0}):
        if _vigente(documento):
            salida[documento["ruc"]] = FichaRuc.model_validate(documento)
    return salida


async def guardar(db: AsyncIOMotorDatabase, ficha: FichaRuc) -> None:
    await _col(db).update_one(
        {"ruc": ficha.ruc}, {"$set": ficha.model_dump()}, upsert=True
    )
