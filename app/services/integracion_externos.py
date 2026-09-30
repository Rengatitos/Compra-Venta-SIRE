"""Paso de los comprobantes de Apaclla Bot a su periodo.

Un comprobante externo pertenece al periodo de su `fecha_operacion`. Mientras
ese periodo no exista se queda en `recibido`; en cuanto existe se busca en el
periodo por su identidad (libro, tipo, serie y número normalizados):

- si ya estaba, no se toca nada y el externo queda `ya_existia`;
- si no, se copia como fila `origen: "externo"` y queda `integrado`.

Cuando la propuesta SUNAT trae después ese mismo comprobante, la fila SIRE
reemplaza a la externa (`reconciliar_con_sunat`).

Los vouchers (Yape, Plin...) no son comprobantes de pago: no se copian como
fila sino que pasan al periodo como pago de un comprobante
(`app.services.pagos_vouchers`).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from bson import ObjectId

from app.domain.comprobante import CERO, Comprobante, Libro, Origen
from app.domain.comprobante_externo import (
    ESTADO_INTEGRADO,
    ESTADO_RECIBIDO,
    ESTADO_YA_EXISTIA,
    es_voucher,
)
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_externos
from app.repositories import periodos as repo_periodos
from app.repositories._mongo import fecha_desde_bson, monto_desde_bson
from app.services import pagos_vouchers

logger = logging.getLogger(__name__)

# Lo que el usuario pudo trabajar sobre la fila externa y que no debe perderse
# cuando la de SUNAT la reemplaza. La glosa va aparte: sólo pasa si la editaron.
_CAMPOS_DEL_USUARIO = ("clasificacion_contable", "clasificacion_estado", "contraparte_manual")


def _monto(valor: Any) -> Decimal | None:
    return monto_desde_bson(valor) if valor is not None else None


def a_comprobante(externo: dict[str, Any]) -> Comprobante:
    """La fila de periodo que corresponde a un comprobante externo."""
    libro = Libro(externo["libro"])
    contraparte = externo.get("contraparte") or {}
    total = _monto(externo.get("total")) or CERO
    igv = _monto(externo.get("igv")) or CERO
    base = _monto(externo.get("base_imponible"))
    if base is None and igv > CERO:
        base = total - igv

    montos: dict[str, Decimal] = {"total": total}
    if igv > CERO:
        montos.update(base_imponible=base or CERO, igv=igv)
        if libro is Libro.COMPRAS:
            # El Registro de Compras sale por destino; sin desglose de SUNAT se
            # asume gravado, que es lo que dice un comprobante con IGV.
            montos.update(base_imponible_dg=base or CERO, igv_dg=igv)
    else:
        montos["no_gravado"] = total

    return Comprobante(
        libro=libro,
        origen=Origen.EXTERNO,
        tipo_cp=externo.get("tipo_cp"),
        serie=externo.get("serie"),
        numero=externo.get("numero"),
        tipo_doc_identidad=contraparte.get("tipo_doc_identidad"),
        documento_contraparte=contraparte.get("documento"),
        razon_social=contraparte.get("nombre"),
        fecha_emision=fecha_desde_bson(externo.get("fecha_operacion")),
        moneda=externo.get("moneda"),
        extra={
            "comprobante_externo_id": str(externo["_id"]),
            "fuente": externo.get("fuente"),
            "confianza": externo.get("confianza"),
            "campos_dudosos": externo.get("campos_dudosos") or [],
            "descripcion_bot": externo.get("descripcion") or "",
        },
        **montos,
    )


async def _integrar(db, empresa_id: str, externo: dict[str, Any]) -> str:
    comprobante = a_comprobante(externo)
    periodo = externo["periodo"]
    existente = await repo_comprobantes.buscar_por_identidad(db, empresa_id, periodo, comprobante)
    if existente and existente.get("origen") != Origen.EXTERNO.value:
        await repo_externos.marcar(db, externo["_id"], ESTADO_YA_EXISTIA, str(existente["_id"]))
        return ESTADO_YA_EXISTIA

    adicionales: dict[str, Any] = {}
    descripcion = (externo.get("descripcion") or "").strip()
    if descripcion:
        adicionales["glosa"] = descripcion
    fila_id = await repo_comprobantes.insertar_externo(
        db, empresa_id, periodo, comprobante, adicionales
    )
    await repo_externos.marcar(db, externo["_id"], ESTADO_INTEGRADO, str(fila_id))
    return ESTADO_INTEGRADO


async def integrar_uno(db, empresa_id: str, externo: dict[str, Any]) -> str:
    """Intenta llevar un externo a su periodo. Devuelve el estado en que queda."""
    if externo.get("estado", ESTADO_RECIBIDO) != ESTADO_RECIBIDO:
        return externo["estado"]
    if not await repo_periodos.obtener(db, empresa_id, externo["periodo"]):
        return ESTADO_RECIBIDO
    if es_voucher(externo):
        return await pagos_vouchers.integrar_voucher(db, empresa_id, externo)
    return await _integrar(db, empresa_id, externo)


async def integrar_pendientes(
    db, empresa_id: str, periodo: str | None = None
) -> dict[str, int]:
    """Integra los externos pendientes cuyo periodo ya existe.

    Con `periodo`, además vuelve a intentar asociar sus vouchers y los del
    periodo siguiente: pueden haber llegado boletas o facturas nuevas desde el
    último refresco.
    """
    conteo = {"integrados": 0, "ya_existian": 0, "vouchers": 0}
    pendientes = await repo_externos.pendientes(
        db, empresa_id, [periodo] if periodo is not None else None
    )
    existentes = (
        await repo_periodos.existentes(db, empresa_id, sorted({p["periodo"] for p in pendientes}))
        if pendientes
        else set()
    )
    con_vouchers: set[str] = {periodo} if periodo is not None else set()
    for externo in pendientes:
        if externo["periodo"] not in existentes:
            continue
        if es_voucher(externo):
            await repo_externos.marcar(db, externo["_id"], ESTADO_INTEGRADO, None)
            con_vouchers.add(externo["periodo"])
            conteo["vouchers"] += 1
            continue
        estado = await _integrar(db, empresa_id, externo)
        conteo["integrados" if estado == ESTADO_INTEGRADO else "ya_existian"] += 1
    # Después de los comprobantes: un voucher puede pagar uno que acaba de entrar.
    for con_voucher in sorted(con_vouchers):
        await pagos_vouchers.asociar_alrededor(db, empresa_id, con_voucher)
    if any(conteo.values()):
        logger.info(
            "Externos integrados empresa=%s periodo=%s integrados=%s ya_existian=%s "
            "vouchers=%s",
            empresa_id, periodo or "todos", conteo["integrados"], conteo["ya_existian"],
            conteo["vouchers"],
        )
    return conteo


async def refrescar(db, empresa_id: str, periodo: str | None = None) -> dict[str, int] | None:
    """`integrar_pendientes` para listados y altas de periodo: si falla, se registra
    y la operación sigue; el siguiente refresco lo vuelve a intentar."""
    try:
        return await integrar_pendientes(db, empresa_id, periodo)
    except Exception:
        logger.exception(
            "No se pudieron integrar los externos empresa=%s periodo=%s",
            empresa_id, periodo or "todos",
        )
        return None


async def reconciliar_con_sunat(db, empresa_id: str, periodo: str, libro: Libro) -> int:
    """Retira las filas externas que la propuesta SUNAT ya trae. Devuelve cuántas."""
    pares = await repo_comprobantes.externos_con_gemela_sire(db, empresa_id, periodo, libro)
    for externa, sire in pares:
        heredados = {
            campo: externa[campo]
            for campo in _CAMPOS_DEL_USUARIO
            if externa.get(campo) and not sire.get(campo)
        }
        glosa = externa.get("glosa")
        descripcion_bot = (externa.get("extra") or {}).get("descripcion_bot") or ""
        if glosa and glosa.strip() != descripcion_bot.strip() and not sire.get("glosa"):
            heredados["glosa"] = glosa
        await repo_comprobantes.completar_campos(db, sire["_id"], heredados)
        await repo_comprobantes.eliminar_por_id(db, externa["_id"])

        externo_id = (externa.get("extra") or {}).get("comprobante_externo_id")
        if externo_id and ObjectId.is_valid(externo_id):
            await repo_externos.marcar(
                db, ObjectId(externo_id), ESTADO_YA_EXISTIA, str(sire["_id"])
            )
    if pares:
        logger.info(
            "Externos reemplazados por la propuesta SUNAT empresa=%s periodo=%s libro=%s "
            "reemplazados=%s",
            empresa_id, periodo, libro.value, len(pares),
        )
    return len(pares)
