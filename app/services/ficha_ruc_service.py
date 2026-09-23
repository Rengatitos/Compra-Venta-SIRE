"""Ficha RUC de SUNAT con caché en Mongo, y su traspaso a la empresa.

La consulta en sí (Playwright + parser) vive en `app/services/sunat/ficha_ruc.py`;
aquí se decide cuándo ir a SUNAT y dónde se guarda lo que vuelve.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.repositories import empresas as repo_empresas
from app.repositories import fichas_ruc as repo_fichas
from app.services.sunat.ficha_ruc import FichaRuc, consultar_fichas, es_ruc

logger = logging.getLogger(__name__)

# La Consulta RUC es un portal público: una consulta a la vez por proceso, en
# vez de abrir un Chromium por cada petición que llegue en paralelo.
_candado = asyncio.Lock()


def actividades_de(ficha: FichaRuc) -> list[dict[str, Any]]:
    """Actividades en la forma de `empresa.actividades_economicas`."""
    return [
        {"tipo": a.tipo, "ciiu": a.ciiu, "descripcion": a.descripcion, "origen": "sunat"}
        for a in ficha.actividades_economicas
    ]


def contexto_de(ficha: FichaRuc) -> dict[str, Any]:
    """Una ficha con la misma forma que un documento de empresa.

    Así el clasificador trata igual a una contraparte registrada que a una que
    sólo se conoce por su ficha.
    """
    return {
        "ruc": ficha.ruc,
        "nombre": ficha.razon_social,
        "actividades_economicas": actividades_de(ficha),
        "ficha_ruc": ficha.model_dump(),
    }


async def _consultar(rucs: list[str]) -> dict[str, FichaRuc | Exception]:
    async with _candado:
        return await asyncio.to_thread(consultar_fichas, rucs)


async def obtener(db, ruc: str, refrescar: bool = False) -> FichaRuc:
    """La ficha de un RUC: de la caché si está vigente, si no de SUNAT.

    Propaga `FichaNoEncontrada` y los fallos del navegador.
    """
    if not refrescar:
        guardada = await repo_fichas.obtener(db, ruc)
        if guardada is not None:
            return guardada
    resultado = (await _consultar([ruc]))[ruc]
    if isinstance(resultado, Exception):
        raise resultado
    await repo_fichas.guardar(db, resultado)
    return resultado


async def obtener_varias(
    db, rucs: list[str], consultar_faltantes: bool = True
) -> dict[str, FichaRuc]:
    """Fichas de varios RUC. Las que SUNAT no devuelve simplemente faltan."""
    rucs = sorted({r for r in rucs if es_ruc(r)})
    fichas = await repo_fichas.obtener_varias(db, rucs)
    faltantes = [r for r in rucs if r not in fichas]
    if faltantes and consultar_faltantes:
        logger.info("Consultando %s fichas RUC en SUNAT", len(faltantes))
        for ruc, resultado in (await _consultar(faltantes)).items():
            if isinstance(resultado, FichaRuc):
                await repo_fichas.guardar(db, resultado)
                fichas[ruc] = resultado
    return fichas


async def actualizar_empresa(db, empresa: dict[str, Any]) -> dict[str, Any]:
    """Consulta de nuevo la ficha de la empresa y guarda sus actividades en ella.

    Devuelve la empresa actualizada. Reemplaza solo las actividades que vinieron
    de SUNAT: las agregadas a mano en Ajustes se conservan, y también la
    actividad elegida para clasificar si sigue en la lista.
    """
    ficha = await obtener(db, empresa["ruc"], refrescar=True)
    de_sunat = actividades_de(ficha)
    codigos = {a["ciiu"] for a in de_sunat}
    manuales = [
        a for a in empresa.get("actividades_economicas") or []
        if a.get("origen") == "manual" and a.get("ciiu") not in codigos
    ]
    actividades = de_sunat + manuales
    cambios: dict[str, Any] = {
        "actividades_economicas": actividades,
        "ficha_ruc": ficha.model_dump(),
    }
    principal = empresa.get("ciiu_principal_clasificacion")
    if principal and principal not in {a["ciiu"] for a in actividades}:
        cambios["ciiu_principal_clasificacion"] = None
    return await repo_empresas.actualizar(db, empresa["_id"], cambios)
