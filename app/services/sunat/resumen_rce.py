"""Resumen oficial del RCE y conciliación monetaria con los comprobantes locales."""

from __future__ import annotations

from typing import Any

import requests

from app.services import plantilla_excel
from app.services.sunat.auth import ErrorSunat, peticion_autenticada

URL_RESUMEN = (
    "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/"
    "resumen/web/resumen/{periodo}/resumencomprobantes/rce/"
)
URL_CONTROL = (
    "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rvierce/"
    "resumen/web/resumeninconsistencias/{periodo}"
)


def normalizar_resumen(datos: Any) -> dict[str, Any]:
    if not isinstance(datos, dict) or not isinstance(datos.get("totales"), dict):
        raise ErrorSunat("SUNAT devolvió un resumen RCE con formato inválido")
    totales = datos["totales"]
    return {
        "cantidad": int(totales.get("cntDocumentos") or 0),
        "base_gravada": str(totales.get("mtoBIGravadoDG") or 0),
        "igv": str(totales.get("mtoIgvIpmDG") or 0),
        "base_gravada_dgng": str(totales.get("mtoBiGravadoDGNG") or 0),
        "igv_dgng": str(totales.get("mtoIgvIpmDGNG") or 0),
        "base_gravada_dng": str(totales.get("mtoBiGravadoDNG") or 0),
        "igv_dng": str(totales.get("mtoIgvIpmDNG") or 0),
        "no_gravado": str(totales.get("mtoValorAdqNG") or 0),
        "isc": str(totales.get("mtoISC") or 0),
        "icbper": str(totales.get("mtoIcbper") or 0),
        "otros": str(totales.get("mtoOtrosTribCargos") or 0),
        "total_original": str(totales.get("mtoTotalCP") or 0),
    }


def normalizar_control(datos: Any) -> dict[str, Any]:
    """Control global mostrado por SUNAT; no representa el detalle por tipo de CDP."""
    if not isinstance(datos, dict):
        raise ErrorSunat("SUNAT devolvió un control RCE con formato inválido")
    cantidad = datos.get("cantidad")
    monto = datos.get("monto")
    if not isinstance(cantidad, dict) or not isinstance(monto, dict):
        raise ErrorSunat("El control RCE de SUNAT no contiene cantidad y monto")
    return {
        "ruc": str(datos.get("numRuc") or ""),
        "periodo": str(datos.get("perPeriodoTributario") or ""),
        "cantidad": int(cantidad.get("total") or 0),
        "total_original": str(monto.get("total") or 0),
        "porcentaje_sin_validaciones": str(
            cantidad.get("porcentajeSinValidaciones") or 0
        ),
    }


async def _obtener_json(db, empresa: dict[str, Any], url: str, params: dict) -> Any:
    def peticion(token: str) -> requests.Response:
        return requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            params=params,
            timeout=60,
        )

    try:
        respuesta = await peticion_autenticada(db, empresa, peticion)
        respuesta.raise_for_status()
        return respuesta.json()
    except requests.Timeout as exc:
        raise ErrorSunat("Timeout consultando el resumen RCE de SUNAT") from exc
    except requests.RequestException as exc:
        codigo = exc.response.status_code if exc.response is not None else "sin respuesta"
        raise ErrorSunat(f"Error {codigo} consultando el resumen RCE de SUNAT") from exc
    except ValueError as exc:
        raise ErrorSunat("SUNAT devolvió JSON inválido en el resumen RCE") from exc


async def obtener(db, empresa: dict[str, Any], periodo: str) -> dict[str, Any]:
    url = URL_RESUMEN.format(periodo=periodo)
    return normalizar_resumen(
        await _obtener_json(db, empresa, url, {"codTipoResumen": "1"})
    )


async def obtener_control(db, empresa: dict[str, Any], periodo: str) -> dict[str, Any]:
    url = URL_CONTROL.format(periodo=periodo)
    return normalizar_control(
        await _obtener_json(
            db,
            empresa,
            url,
            {"codTipoResumen": "1", "codLibro": "080000"},
        )
    )


def conciliar(
    resumen_original: dict[str, Any],
    comprobantes: list[dict[str, Any]],
    control_global: dict[str, Any] | None = None,
) -> dict[str, Any]:
    procesamiento = plantilla_excel.auditar_conversion(comprobantes)
    advertencias = []
    if resumen_original["cantidad"] != len(comprobantes):
        advertencias.append(
            f"El resumen de propuesta informa {resumen_original['cantidad']} comprobantes "
            f"y se procesaron {len(comprobantes)}"
        )
    if control_global is not None and control_global["cantidad"] != len(comprobantes):
        advertencias.append(
            "El resumen de inconsistencias tiene un conteo distinto al detalle de la "
            "propuesta; se conserva como indicador informativo"
        )
    return {
        "resumen_sire_original": resumen_original,
        "control_global_sire": control_global,
        "procesamiento_pen": procesamiento,
        # La propuesta descargable es la fuente de filas. El resumen de
        # inconsistencias mide un universo de validaciones diferente.
        "cantidad_coincide": resumen_original["cantidad"] == len(comprobantes),
        "advertencias": advertencias,
    }
