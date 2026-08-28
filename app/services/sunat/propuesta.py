from __future__ import annotations

import json
import logging
from typing import Any

import requests
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.domain.comprobante import Comprobante, Libro, Origen
from app.services.sunat.auth import ErrorSunat, peticion_autenticada

logger = logging.getLogger(__name__)

# Solo facturas y recibos por honorarios; las boletas del RCE se descartan.
PREFIJOS_SERIE_ACEPTADOS = ("F", "E")

_CAMPOS_SERIE = ("numSerieCDP", "numSerie", "desSerieCDP")
_CAMPOS_NUMERO = ("numCDP", "numComprobante", "numCorrelativo")
_CAMPOS_TIPO_CP = ("codTipoCDP", "codTipoComprobante", "codTipoDocumento")
_CAMPOS_DOC_CONTRAPARTE = ("numDocIdentidadProveedor", "numRucProveedor", "numRuc")
_CAMPOS_TIPO_DOC = ("codTipoDocIdentidadProveedor", "codTipoDocIdentidad")
_CAMPOS_RAZON_SOCIAL = (
    "desRazonSocialProveedor",
    "nomRazonSocialProveedor",
    "desProveedor",
    "desRazonSocialEmisor",
    "nomRazonSocialEmisor",
)
_CAMPOS_FECHA_EMISION = ("fecEmision", "fecEmisionCDP")
_CAMPOS_FECHA_VENCIMIENTO = ("fecVencimiento", "fecVcto")
_CAMPOS_MONEDA = ("codMoneda", "desMoneda")
_CAMPOS_TIPO_CAMBIO = ("mtoTipoCambio", "valTipoCambio")

_MONTOS = {
    "base_imponible": ("mtoBIGravada", "mtoBaseImponible", "mtoBaseImponibleGravada"),
    "igv": ("mtoIGV", "mtoIgvIpm"),
    "exonerado": ("mtoExonerado", "mtoOperExonerada"),
    "inafecto": ("mtoInafecto", "mtoOperInafecta"),
    "isc": ("mtoISC",),
    "otros_tributos": ("mtoOtrosTributos", "mtoOtrosCargos"),
    "total": ("mtoTotalCp", "mtoImporteTotal"),
}


def _primero(datos: dict[str, Any], campos: tuple[str, ...], defecto: Any = "") -> Any:
    for campo in campos:
        valor = datos.get(campo)
        if valor not in (None, "", "0"):
            return valor
    return defecto


def _url_propuesta(periodo: str) -> str:
    plantilla = (settings.URL_SIRE_PROPUESTA or "").strip()
    if not plantilla:
        raise ErrorSunat("URL_SIRE_PROPUESTA no está configurada en el entorno")
    return plantilla.replace("{PERIODO}", periodo)


def a_comprobante(registro: dict[str, Any], libro: Libro) -> Comprobante:
    montos_crudos = registro.get("montos") or {}
    fuente_montos = {**registro, **montos_crudos}

    montos = {
        destino: _primero(fuente_montos, candidatos, 0)
        for destino, candidatos in _MONTOS.items()
    }

    return Comprobante(
        libro=libro,
        origen=Origen.SIRE,
        tipo_cp=_primero(registro, _CAMPOS_TIPO_CP),
        serie=_primero(registro, _CAMPOS_SERIE),
        numero=_primero(registro, _CAMPOS_NUMERO),
        tipo_doc_identidad=_primero(registro, _CAMPOS_TIPO_DOC),
        documento_contraparte=_primero(registro, _CAMPOS_DOC_CONTRAPARTE),
        razon_social=_primero(registro, _CAMPOS_RAZON_SOCIAL),
        fecha_emision=_primero(registro, _CAMPOS_FECHA_EMISION, None),
        fecha_vencimiento=_primero(registro, _CAMPOS_FECHA_VENCIMIENTO, None),
        moneda=_primero(registro, _CAMPOS_MONEDA, "PEN"),
        tipo_cambio=_primero(registro, _CAMPOS_TIPO_CAMBIO, None),
        extra={"raw_sire": json.dumps(registro, ensure_ascii=False)},
        **montos,
    )


def serie_aceptada(comprobante: Comprobante) -> bool:
    return comprobante.serie.upper().startswith(PREFIJOS_SERIE_ACEPTADOS)


def pertenece_al_periodo(comprobante: Comprobante, periodo: str) -> bool:
    if comprobante.fecha_emision is None:
        return False
    return comprobante.fecha_emision.strftime("%Y%m") == periodo


async def descargar(
    db: AsyncIOMotorDatabase,
    empresa: dict[str, Any],
    periodo: str,
    libro: Libro,
) -> list[dict[str, Any]] | None:
    if libro is not Libro.COMPRAS:
        raise ErrorSunat(
            "La descarga de propuesta solo está implementada para el libro de compras (RCE)"
        )

    url = _url_propuesta(periodo)
    params = {"page": 1, "perPage": 100, "codTipoOpe": "1"}

    def peticion(token: str) -> requests.Response:
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
    if respuesta.status_code == 422:
        return None

    if respuesta.status_code != 200:
        logger.error(
            "Error no controlado del SIRE ruc=%s periodo=%s status=%s body=%s",
            empresa.get("ruc"),
            periodo,
            respuesta.status_code,
            respuesta.text[:1000],
        )
        raise ErrorSunat(f"Error {respuesta.status_code} del SIRE: {respuesta.text[:500]}")

    datos = respuesta.json()
    if isinstance(datos, list):
        return datos
    return datos.get("registros", [])
