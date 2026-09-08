"""Ciclo completo del ticket que genera el ZIP oficial de propuesta RCE."""

from __future__ import annotations

import asyncio
from typing import Any

import requests

from app.services.sunat.auth import ErrorSunat, peticion_autenticada

URL_GENERAR = (
    "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/"
    "propuesta/web/propuesta/{periodo}/exportacioncomprobantepropuesta"
)
URL_ESTADO = (
    "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/"
    "gestionprocesosmasivos/web/masivo/consultaestadotickets"
)
URL_ARCHIVO = (
    "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/"
    "gestionprocesosmasivos/web/masivo/archivoreporte"
)
COD_LIBRO_RCE = "080000"
# La exportacion de la propuesta del portal SIRE se registra con origen 1.
COD_ORIGEN_PROPUESTA = "1"


async def _peticion(db, empresa: dict[str, Any], funcion) -> requests.Response:
    try:
        respuesta = await peticion_autenticada(db, empresa, funcion)
    except requests.Timeout as exc:
        raise ErrorSunat("Timeout durante el ciclo del ticket RCE") from exc
    except requests.RequestException as exc:
        raise ErrorSunat(f"Error de conexión durante el ticket RCE: {exc}") from exc
    try:
        respuesta.raise_for_status()
    except requests.RequestException as exc:
        raise ErrorSunat(
            f"SUNAT respondió {respuesta.status_code} durante el ticket RCE: "
            f"{respuesta.text[:300]}"
        ) from exc
    return respuesta


async def generar(db, empresa: dict[str, Any], periodo: str) -> str:
    url = URL_GENERAR.format(periodo=periodo)

    def hacer(token: str) -> requests.Response:
        return requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={"codTipoArchivo": "1", "codOrigenEnvio": COD_ORIGEN_PROPUESTA},
            timeout=60,
        )

    respuesta = await _peticion(db, empresa, hacer)
    try:
        numero = str(respuesta.json().get("numTicket") or "").strip()
    except ValueError as exc:
        raise ErrorSunat("SUNAT devolvió JSON inválido al generar el ticket RCE") from exc
    if not numero:
        raise ErrorSunat("SUNAT no devolvió numTicket al generar la propuesta RCE")
    return numero


def _buscar_archivo(valor: Any) -> dict[str, str] | None:
    """Encuentra los metadatos del ZIP pese a variaciones de forma entre versiones."""
    if isinstance(valor, dict):
        nombre = valor.get("nomArchivoReporte")
        if nombre:
            # SUNAT publica actualmente `codTipoAchivoReporte` (sin la r),
            # aunque otros contratos/documentaciones usan el nombre correcto.
            tipo_archivo = valor.get("codTipoArchivoReporte")
            if tipo_archivo is None:
                tipo_archivo = valor.get("codTipoAchivoReporte")
            return {
                "nomArchivoReporte": str(nombre),
                "codTipoArchivoReporte": str(tipo_archivo or "00"),
                "codProceso": str(valor.get("codProceso") or ""),
                "perTributario": str(valor.get("perTributario") or ""),
            }
        for hijo in valor.values():
            encontrado = _buscar_archivo(hijo)
            if encontrado:
                # Algunos campos viven en el registro padre, no junto al archivo.
                for campo in ("codProceso", "perTributario"):
                    if not encontrado[campo] and valor.get(campo) is not None:
                        encontrado[campo] = str(valor[campo])
                return encontrado
    elif isinstance(valor, list):
        for hijo in valor:
            encontrado = _buscar_archivo(hijo)
            if encontrado:
                return encontrado
    return None


def _registro_del_ticket(datos: Any, ticket: str) -> dict[str, Any] | None:
    if not isinstance(datos, dict) or not isinstance(datos.get("registros"), list):
        return None
    for registro in datos["registros"]:
        if not isinstance(registro, dict):
            continue
        detalle = registro.get("detalleTicket")
        ticket_registro = registro.get("numTicket")
        if not ticket_registro and isinstance(detalle, dict):
            ticket_registro = detalle.get("numTicket")
        if str(ticket_registro or "").strip() == ticket:
            return registro
    return None


async def consultar(
    db, empresa: dict[str, Any], periodo: str, ticket: str
) -> dict[str, str] | None:
    def hacer(token: str) -> requests.Response:
        return requests.get(
            URL_ESTADO,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params={
                "perIni": periodo,
                "perFin": periodo,
                "page": 1,
                "perPage": 20,
                "numTicket": ticket,
                "codOrigenEnvio": COD_ORIGEN_PROPUESTA,
                "codLibro": COD_LIBRO_RCE,
            },
            timeout=60,
        )

    respuesta = await _peticion(db, empresa, hacer)
    try:
        datos = respuesta.json()
    except ValueError as exc:
        raise ErrorSunat("SUNAT devolvió JSON inválido consultando el ticket RCE") from exc
    registro = _registro_del_ticket(datos, ticket)
    if registro is None:
        return None

    detalle = registro.get("detalleTicket")
    codigo = str(registro.get("codEstadoProceso") or "").strip()
    descripcion = str(registro.get("desEstadoProceso") or "").strip()
    if isinstance(detalle, dict):
        codigo = codigo or str(detalle.get("codEstadoEnvio") or "").strip()
        descripcion = descripcion or str(detalle.get("desEstadoEnvio") or "").strip()

    descripcion_normalizada = descripcion.casefold()
    estados_fallidos = {"rechazado", "error", "fallido", "cancelado"}
    if descripcion_normalizada in estados_fallidos:
        raise ErrorSunat(
            f"SUNAT marcó el ticket RCE {ticket} como {descripcion or codigo}"
        )

    # El portal habilita el reporte con estado 06 (Terminado). Durante los
    # demás estados el ticket sigue procesándose y debe volver a consultarse.
    terminado = codigo == "06" or descripcion_normalizada == "terminado"
    descargable = str(registro.get("showReporteDescarga") or "") == "1"
    if not terminado and not descargable:
        return None
    return _buscar_archivo(registro)


async def descargar(
    db, empresa: dict[str, Any], periodo: str, ticket: str, archivo: dict[str, str]
) -> bytes:
    def hacer(token: str) -> requests.Response:
        return requests.get(
            URL_ARCHIVO,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/zip"},
            params={
                "nomArchivoReporte": archivo["nomArchivoReporte"],
                "codTipoArchivoReporte": archivo["codTipoArchivoReporte"],
                "codLibro": COD_LIBRO_RCE,
                "perTributario": archivo["perTributario"] or periodo,
                "codProceso": archivo["codProceso"] or "10",
                "numTicket": ticket,
            },
            timeout=60,
        )

    return (await _peticion(db, empresa, hacer)).content


async def obtener_zip(
    db,
    empresa: dict[str, Any],
    periodo: str,
    intentos: int = 30,
    intervalo: float = 2.0,
) -> tuple[str, bytes]:
    ticket = await generar(db, empresa, periodo)
    for intento in range(intentos):
        archivo = await consultar(db, empresa, periodo, ticket)
        if archivo:
            return ticket, await descargar(db, empresa, periodo, ticket, archivo)
        if intento + 1 < intentos:
            await asyncio.sleep(intervalo)
    raise ErrorSunat(f"El ticket RCE {ticket} no terminó dentro del tiempo de espera")
