"""Clasificación contable de los comprobantes guardados.

Traduce un comprobante de Mongo a la entrada del motor RAG + Gemini
(`app/services/clasificador`), lo clasifica y guarda el resultado en el propio
comprobante, en `clasificacion_contable`. De ahí lo leen la respuesta del
comprobante y la exportación a Excel, que escribe la cuenta base sólo cuando
el clasificador no pide revisión.

El motor recibe hechos, no una preclasificación: los ítems del detalle SUNAT
(o, a falta de ellos, la glosa), los importes, el tipo de comprobante y las
actividades económicas (CIIU) de la empresa y de la contraparte. Esas
actividades salen de la ficha RUC de SUNAT (`ficha_ruc_service`): la de la
empresa se guarda en ella la primera vez que hace falta, y las de las
contrapartes quedan en caché.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.domain import rubro
from app.domain.comprobante import Libro, normalizar_monto
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.services import ficha_ruc_service
from app.services.clasificador.motor import MotorNoDisponible, motor
from app.services.clasificador.schemas import (
    ClassificationResponse,
    ClassifyRequest,
    CompanyContext,
    Counterparty,
    EconomicActivity,
    PeriodContext,
    Voucher,
    VoucherItem,
    VoucherType,
)
from app.services.comprobante_service import serializar
from app.services.glosa import ESTADO_CON_GLOSA, estado_glosa
from app.services.jobs_service import Reportador
from app.services.sunat.ficha_ruc import es_ruc

logger = logging.getLogger(__name__)

__all__ = ["MotorNoDisponible", "clasificar_comprobante", "clasificar_periodo"]


class SinDescripcion(ValueError):
    """El comprobante no trae ítems ni glosa: no hay operación que clasificar."""


def _numero(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    return float(normalizar_monto(valor))


def _actividades(empresa: dict[str, Any] | None) -> list[EconomicActivity]:
    """Actividades registradas; si no hay, el CIIU principal del token SUNAT.

    `empresa` es un documento de empresa o el contexto de una ficha RUC
    (`ficha_ruc_service.contexto_de`), que tienen la misma forma.
    """
    if not empresa:
        return []
    actividades = [
        EconomicActivity(
            tipo=a.get("tipo"), ciiu_v4=a.get("ciiu"), descripcion=a.get("descripcion")
        )
        for a in empresa.get("actividades_economicas") or []
        if isinstance(a, dict) and a.get("ciiu")
    ]
    if actividades:
        return actividades
    ciiu = rubro.ciiu_desde_token_sunat(empresa.get("sunat_token") or "")
    return [EconomicActivity(tipo="PRINCIPAL", ciiu_v4=ciiu)] if ciiu else []


def _ficha(contexto: dict[str, Any] | None) -> dict[str, Any]:
    return (contexto or {}).get("ficha_ruc") or {}


def _items(visible: dict[str, Any]) -> list[VoucherItem]:
    items = [
        VoucherItem(
            descripcion=item["descripcion"].strip(),
            codigo=str(item.get("codigo") or "").strip() or None,
            cantidad=_numero(item.get("cantidad")),
            unidad_medida=str(item.get("unidad_medida") or "").strip() or None,
            valor_unitario=_numero(item.get("valor_unitario")),
            precio_unitario=_numero(item.get("precio_unitario")),
            valor_venta=_numero(item.get("valor_venta")),
        )
        for item in visible.get("detalle_sunat") or []
        if isinstance(item, dict) and str(item.get("descripcion") or "").strip()
    ]
    if items:
        return items
    # Sin ítems, la glosa (manual o sacada de la leyenda) describe la operación.
    glosa = (visible.get("glosa") or "").strip()
    return [VoucherItem(descripcion=glosa)] if glosa else []


def construir_solicitud(
    documento: dict[str, Any],
    empresa: dict[str, Any],
    contraparte: dict[str, Any] | None = None,
) -> ClassifyRequest:
    """Entrada del clasificador para un comprobante de Mongo.

    `contraparte` es la empresa registrada con el RUC de la contraparte o el
    contexto de su ficha RUC, si lo hay: sus actividades ayudan a interpretar
    la operación.
    """
    visible = serializar(documento)
    items = _items(visible)
    if not items:
        raise SinDescripcion(
            f"El comprobante {visible['serie_numero']} no tiene ítems ni glosa que clasificar"
        )

    libro = str(visible["libro"]).upper()
    fecha = visible.get("fecha_emision")
    ficha_empresa = _ficha(empresa)
    ficha_contraparte = _ficha(contraparte)
    return ClassifyRequest(
        empresa=CompanyContext(
            ruc=empresa["ruc"],
            razon_social=empresa.get("nombre") or ficha_empresa.get("razon_social"),
            actividades_economicas=_actividades(empresa),
            comprobantes_autorizados_impresion=ficha_empresa.get("comprobantes_autorizados") or [],
            sistema_emision_electronica=[
                {"descripcion": s} for s in ficha_empresa.get("sistema_emision_electronica") or []
            ],
            emisor_electronico_desde=ficha_empresa.get("emisor_electronico_desde") or None,
            comprobantes_electronicos=ficha_empresa.get("comprobantes_electronicos") or [],
        ),
        contexto_periodo=PeriodContext(periodo=documento.get("periodo"), libro=libro),
        comprobante=Voucher(
            libro=libro,
            tipo_cp=VoucherType(
                codigo=visible["tipo_cp"], descripcion=visible["tipo_cp_descripcion"]
            ),
            serie=visible["serie"],
            numero=visible["numero"],
            fecha_emision=fecha.isoformat() if fecha else None,
            contraparte=Counterparty(
                tipo_documento=visible.get("tipo_doc_identidad") or None,
                numero_documento=visible.get("documento_contraparte") or None,
                razon_social=visible.get("razon_social") or None,
                actividades_economicas=_actividades(contraparte),
                comprobantes_autorizados=ficha_contraparte.get("comprobantes_autorizados") or [],
                sistema_emision_electronica=[
                    {"descripcion": s}
                    for s in ficha_contraparte.get("sistema_emision_electronica") or []
                ],
            ),
            moneda=visible.get("moneda"),
            origen=str(visible.get("origen") or "").upper(),
            importes={
                campo: visible.get(campo)
                for campo in (
                    "base_imponible", "igv", "exonerado", "inafecto",
                    "no_gravado", "icbper", "otros_tributos", "total",
                )
            },
        ),
        items=items,
    )


def a_documento(respuesta: ClassificationResponse, modelo: str) -> dict[str, Any]:
    def cuenta(valor):
        return valor.model_dump() if valor else None

    return {
        "cuenta_base": cuenta(respuesta.cuenta_base_imponible),
        "cuenta_total": cuenta(respuesta.cuenta_total),
        "clasificacion": respuesta.clasificacion,
        "subtipo": respuesta.subtipo,
        "condicion_igv": respuesta.condicion_igv,
        "centro_costos": respuesta.centro_costos,
        "confianza": respuesta.confianza,
        "confianza_rag": respuesta.confianza_rag,
        "requiere_revision": respuesta.requiere_revision,
        "razon": respuesta.razon,
        "modelo": modelo,
        "clasificado_en": datetime.now(UTC),
    }


async def _asegurar_actividades_empresa(db, empresa: dict) -> dict:
    """La empresa con sus actividades; si no tiene, las trae de su ficha RUC.

    Un fallo de SUNAT no impide clasificar: se sigue con el CIIU del token.
    """
    if empresa.get("actividades_economicas"):
        return empresa
    try:
        return await ficha_ruc_service.actualizar_empresa(db, empresa)
    except Exception as exc:
        logger.warning("Sin ficha RUC para la empresa %s: %s", empresa.get("ruc"), exc)
        return empresa


async def contextos_contrapartes(
    db, empresa: dict, documentos: list[dict], consultar_faltantes: bool
) -> dict[str, dict]:
    """Contexto de cada contraparte con RUC, por RUC.

    Primero la empresa registrada con ese RUC (si tiene actividades); si no,
    su ficha RUC, de la caché o —con `consultar_faltantes`— de SUNAT.
    """
    rucs = {str(d.get("documento_contraparte") or "").strip() for d in documentos}
    rucs = {r for r in rucs if es_ruc(r) and r != empresa.get("ruc")}
    contextos: dict[str, dict] = {}
    for ruc in rucs:
        registrada = await repo_empresas.obtener_por_ruc(db, ruc)
        if registrada and registrada.get("actividades_economicas"):
            contextos[ruc] = registrada
    try:
        fichas = await ficha_ruc_service.obtener_varias(
            db, sorted(rucs - set(contextos)), consultar_faltantes=consultar_faltantes
        )
    except Exception as exc:
        logger.warning("No se pudieron consultar las fichas RUC de las contrapartes: %s", exc)
        fichas = {}
    for ruc, ficha in fichas.items():
        contextos[ruc] = ficha_ruc_service.contexto_de(ficha)
    return contextos


async def _clasificar(db, empresa, documento, contextos: dict[str, dict]) -> dict[str, Any]:
    ruc_contraparte = str(documento.get("documento_contraparte") or "").strip()
    solicitud = construir_solicitud(documento, empresa, contextos.get(ruc_contraparte))
    # El motor es síncrono (embeddings en CPU y llamadas bloqueantes a
    # Gemini): en el hilo del loop congelaría la API entera.
    clasificador = await asyncio.to_thread(motor.obtener)
    respuesta = await asyncio.to_thread(clasificador.classify, solicitud)
    resultado = a_documento(respuesta, motor.settings.gemini_model)
    await repo_comprobantes.guardar_clasificacion(db, documento["_id"], resultado)
    return resultado


async def clasificar_comprobante(db, empresa: dict, documento: dict) -> dict[str, Any]:
    """Clasifica un comprobante y guarda el resultado. Propaga `SinDescripcion`."""
    empresa = await _asegurar_actividades_empresa(db, empresa)
    contextos = await contextos_contrapartes(db, empresa, [documento], consultar_faltantes=True)
    return await _clasificar(db, empresa, documento, contextos)


async def clasificar_periodo(
    db,
    empresa: dict,
    periodo: str,
    libro: Libro,
    reportar: Reportador,
    reclasificar: bool = False,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    pendientes = await repo_comprobantes.listar_para_clasificar(
        db, empresa_id, periodo, libro, reclasificar
    )
    # Solo los comprobantes «con glosa», con la misma regla que la columna
    # «Estado glosa»: sin descripción de la operación, lo que saliera sería una
    # cuenta adivinada. Los demás esperan a que se complete la glosa.
    con_glosa = [d for d in pendientes if estado_glosa(d) == ESTADO_CON_GLOSA]
    documentos = con_glosa[: settings.CLASIFICADOR_MAX_COMPROBANTES]
    total = len(documentos)
    # Antes de nada: si el motor no arranca, que el trabajo falle con ese
    # motivo y no con un error repetido por cada comprobante.
    await reportar(0, total, "Cargando el clasificador contable")
    await asyncio.to_thread(motor.obtener)

    await reportar(0, total, "Consultando actividades económicas (CIIU) en SUNAT")
    empresa = await _asegurar_actividades_empresa(db, empresa)
    contextos = await contextos_contrapartes(
        db, empresa, documentos, settings.CLASIFICADOR_CONSULTAR_CONTRAPARTES
    )

    conteo = {"clasificados": 0, "requieren_revision": 0, "sin_descripcion": 0, "errores": 0}
    errores: list[dict[str, str]] = []
    for i, documento in enumerate(documentos, start=1):
        serie_numero = documento.get("serie_numero", "")
        await reportar(i - 1, total, f"Clasificando {serie_numero}")
        try:
            resultado = await _clasificar(db, empresa, documento, contextos)
        except SinDescripcion:
            conteo["sin_descripcion"] += 1
            continue
        except Exception as exc:
            # Un fallo de Gemini en un comprobante no tumba el lote: queda sin
            # clasificar y entra en la siguiente vuelta.
            logger.warning("No se pudo clasificar %s: %s", serie_numero, exc)
            conteo["errores"] += 1
            errores.append({"serie_numero": serie_numero, "error": str(exc)[:300]})
            continue
        conteo["clasificados"] += 1
        conteo["requieren_revision"] += int(resultado["requiere_revision"])

    await reportar(total, total, "Clasificación terminada")
    # Los que el tope dejó fuera, más los que fallaron: entran en otra vuelta.
    restantes = len(con_glosa) - total + conteo["errores"]
    return {
        **conteo,
        # Pendientes del libro que no se tocaron por no tener glosa todavía.
        "sin_glosa_omitidos": len(pendientes) - len(con_glosa),
        "contrapartes_con_ciiu": len(contextos),
        "pendientes_restantes": restantes,
        "detalle_errores": errores[:20],
    }


def estado_motor() -> dict[str, Any]:
    return {
        "habilitado": settings.CLASIFICADOR_HABILITADO,
        **motor.describir(),
    }
