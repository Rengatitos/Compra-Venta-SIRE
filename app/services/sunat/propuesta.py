"""Descarga de la propuesta del SIRE y despacho del mapeo por libro.

Este módulo se queda con el transporte —URL, credenciales, paginación— y delega
la traducción de cada registro a `rce.py` (compras) o `rvie.py` (ventas), que
son los que conocen los nombres de campo de cada libro.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.domain.comprobante import Comprobante, Libro
from app.services.sunat import rce, rvie
from app.services.sunat.auth import ErrorSunat, peticion_autenticada

logger = logging.getLogger(__name__)

_MAPEOS = {Libro.COMPRAS: rce.a_comprobante, Libro.VENTAS: rvie.a_comprobante}

# El SIRE rechaza con 422 cualquier `perPage` por encima de 100, en los dos
# libros. Se recorta en vez de dejar que la configuración tumbe la descarga
# entera con un error de validación que no dice de dónde sale el número.
MAX_PER_PAGE = 100

# `codTipoOpe` es propio del RCE (distingue adquisiciones de importaciones); el
# RVIE no lo acepta.
_PARAMS = {Libro.COMPRAS: {"codTipoOpe": "1"}, Libro.VENTAS: {}}


def _url(libro: Libro, periodo: str) -> str:
    plantilla = (
        settings.URL_SIRE_PROPUESTA
        if libro is Libro.COMPRAS
        else settings.URL_SIRE_PROPUESTA_VENTAS
    )
    plantilla = (plantilla or "").strip()
    if not plantilla:
        variable = (
            "URL_SIRE_PROPUESTA"
            if libro is Libro.COMPRAS
            else "URL_SIRE_PROPUESTA_VENTAS"
        )
        raise ErrorSunat(f"{variable} no está configurada en el entorno")
    return plantilla.replace("{PERIODO}", periodo)


def _pagina(datos: Any) -> tuple[list[dict[str, Any]], int | None]:
    """Registros de la página y cuántos hay en total, si SUNAT lo dice.

    Los dos libros responden `{paginacion: {page, perPage, totalRegistros},
    registros: [...], totales: {...}}`. El total es lo que permite cerrar el
    recorrido sin pedir una página de más y, sobre todo, detectar un endpoint
    que ignore `page` y devuelva siempre lo mismo.
    """
    if isinstance(datos, list):
        return datos, None
    if not isinstance(datos, dict):
        return [], None

    registros = datos.get("registros") or []
    paginacion = datos.get("paginacion")
    total = paginacion.get("totalRegistros") if isinstance(paginacion, dict) else None
    return registros, total if isinstance(total, int) else None


def a_comprobante(registro: dict[str, Any], libro: Libro) -> Comprobante:
    return _MAPEOS[libro](registro)


def pertenece_al_periodo(comprobante: Comprobante, periodo: str) -> bool:
    """Si el comprobante entra en el registro de ese periodo.

    Manda el periodo tributario que asigna SUNAT (`perTributario`), no el mes
    de emisión. Comparar por emisión descartaba las facturas de un mes anotadas
    en el siguiente, que son legales —el crédito fiscal del IGV puede tomarse
    después— y que SUNAT devuelve precisamente porque pertenecen al periodo
    pedido. En un caso real eso tiraba 27 de 87 compras, S/ 3.101,89 con su
    crédito, sin que nada lo dijera salvo el contador de `descartados`.

    Sin ese dato se cae al mes de emisión, que es lo único que queda.
    """
    periodo_sunat = str(comprobante.extra.get("periodo_sunat") or "").strip()
    if periodo_sunat:
        return periodo_sunat == periodo
    if comprobante.fecha_emision is None:
        return False
    return comprobante.fecha_emision.strftime("%Y%m") == periodo


async def descargar(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    libro: Libro,
) -> list[dict[str, Any]] | None:
    """Todos los registros de la propuesta, o `None` si SUNAT no tiene ninguna.

    Recorre las páginas hasta que una venga incompleta. Antes se pedía
    `page=1&perPage=100` fijo y cualquier periodo con más de cien comprobantes
    se truncaba sin decir nada; en ventas eso es la norma, no la excepción.
    """
    url = _url(libro, periodo)
    por_pagina = min(settings.SIRE_PER_PAGE, MAX_PER_PAGE)
    if settings.SIRE_PER_PAGE > MAX_PER_PAGE:
        logger.warning(
            "SIRE_PER_PAGE=%s excede el máximo del SIRE; se piden %s por página",
            settings.SIRE_PER_PAGE,
            MAX_PER_PAGE,
        )
    registros: list[dict[str, Any]] = []

    for pagina in range(1, settings.SIRE_MAX_PAGINAS + 1):
        params = {**_PARAMS[libro], "page": pagina, "perPage": por_pagina}

        def peticion(token: str, params: dict[str, Any] = params) -> requests.Response:
            return requests.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                params=params,
                timeout=60,
            )

        respuesta = await peticion_autenticada(db, empresa, peticion)

        # 422 significa "no hay propuesta para ese periodo", no es un error.
        # Pasada la primera página sólo quiere decir que ya no quedan más.
        if respuesta.status_code == 422:
            return None if pagina == 1 else registros

        if respuesta.status_code != 200:
            logger.error(
                "Error no controlado del SIRE ruc=%s periodo=%s libro=%s página=%s "
                "status=%s body=%s",
                empresa.get("ruc"),
                periodo,
                libro.value,
                pagina,
                respuesta.status_code,
                respuesta.text[:1000],
            )
            raise ErrorSunat(f"Error {respuesta.status_code} del SIRE: {respuesta.text[:500]}")

        lote, total = _pagina(respuesta.json())
        registros.extend(lote)

        if not lote or len(lote) < por_pagina:
            return registros
        if total is not None and len(registros) >= total:
            return registros

    # Salir por el tope no es normal: o el periodo es enorme o el endpoint
    # ignora `page` y devuelve siempre lo mismo. En cualquiera de los dos casos
    # el registro queda incompleto y hay que saberlo.
    logger.warning(
        "Paginación cortada por SIRE_MAX_PAGINAS ruc=%s periodo=%s libro=%s registros=%s",
        empresa.get("ruc"),
        periodo,
        libro.value,
        len(registros),
    )
    return registros
