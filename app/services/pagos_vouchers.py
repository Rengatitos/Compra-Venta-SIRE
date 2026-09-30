"""Los vouchers de Apaclla Bot como pagos de los comprobantes.

Un voucher (Yape, Plin, Mercado Pago, Niubiz) no es un comprobante de pago: es
la prueba de cómo se pagó o se cobró una boleta o factura. Por eso no se copia
como fila de `comprobantes`; queda en `comprobantes_externos` y apunta al
comprobante que paga con `pago_de`, su identidad (periodo, libro, tipo, serie y
número). La identidad, y no el `_id`, porque es lo que sobrevive a que la fila
SUNAT reemplace a la externa, a una resincronización y a borrar y recrear el
periodo.

- Mientras su periodo (el de su fecha) no existe, el voucher queda `recibido`.
- En cuanto existe, queda `integrado`: se ve en su periodo, asociado o no.
- Puede pagar un comprobante de su periodo o del anterior: un Yape del 2 de
  octubre suele cobrar una boleta de fines de septiembre. El pago se ve en el
  comprobante, en el periodo de éste.
- La asociación automática sólo lo asocia si hay una única candidata entre los
  dos periodos; si no, queda «sin comprobante» hasta que alguien lo asocie a
  mano.

En la plantilla Contasis, la fila del comprobante lleva el medio de pago y el
número de operación de sus vouchers; los que no tienen comprobante van a una
hoja aparte (`plantilla_excel`).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from bson import ObjectId

from app.domain import periodo as dominio_periodo
from app.domain.comprobante import (
    Libro,
    montos_iguales,
    normalizar_documento,
)
from app.domain.comprobante_externo import (
    ASOCIACION_AUTO,
    ASOCIACION_MANUAL,
    ESTADO_INTEGRADO,
    MEDIO_PAGO_POR_FUENTE,
    NOMBRE_FUENTE,
)
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import comprobantes_externos as repo_externos
from app.repositories._mongo import fecha_desde_bson, monto_desde_bson

logger = logging.getLogger(__name__)

# (periodo, libro, tipo_cp, serie, numero)
Identidad = tuple[str, str, str, str, str]

# Una nota de crédito o débito no se paga con un voucher.
_TIPOS_QUE_NO_SE_PAGAN = frozenset({"07", "08", "87", "88", "97", "98"})


class VoucherNoEncontrado(Exception):
    pass


class ComprobanteNoEncontrado(Exception):
    pass


def periodos_que_puede_pagar(periodo: str) -> list[str]:
    """El periodo del voucher y el anterior, en ese orden."""
    return [periodo, dominio_periodo.anterior(periodo)]


def identidad(fila: dict[str, Any], periodo: str | None = None) -> Identidad:
    """`periodo` completa la identidad de una fila serializada, que no lo trae."""
    return (
        str(fila.get("periodo") or periodo or ""),
        str(fila.get("libro") or ""),
        str(fila.get("tipo_cp") or ""),
        str(fila.get("serie") or ""),
        str(fila.get("numero") or ""),
    )


def _pago_de(fila: dict[str, Any]) -> dict[str, str]:
    periodo, libro, tipo_cp, serie, numero = identidad(fila)
    return {
        "periodo": periodo, "libro": libro, "tipo_cp": tipo_cp, "serie": serie, "numero": numero
    }


def _identidad_asociada(voucher: dict[str, Any]) -> Identidad | None:
    pago_de = voucher.get("pago_de")
    # Un `pago_de` sin periodo es de antes de que un voucher pudiera pagar el
    # periodo anterior: siempre apuntaba al suyo.
    return identidad(pago_de, voucher.get("periodo")) if pago_de else None


def _monto(valor: Any):
    return monto_desde_bson(valor) if valor is not None else None


def _texto_monto(valor: Any) -> str | None:
    monto = _monto(valor)
    return f"{monto:.2f}" if monto is not None else None


def _iso(valor: Any) -> str | None:
    fecha = fecha_desde_bson(valor)
    return fecha.isoformat() if isinstance(fecha, date) else None


def presentar(voucher: dict[str, Any]) -> dict[str, Any]:
    """Un voucher tal como sale en la API y en la plantilla."""
    fuente = voucher.get("fuente") or ""
    contraparte = voucher.get("contraparte") or {}
    return {
        "id": str(voucher["_id"]),
        "periodo": voucher.get("periodo"),
        "libro": voucher.get("libro"),
        "fuente": fuente,
        "medio_pago": NOMBRE_FUENTE.get(fuente, fuente.replace("_", " ").title()),
        "codigo_medio_pago": MEDIO_PAGO_POR_FUENTE.get(fuente, "999"),
        "nro_operacion": voucher.get("nro_operacion") or "",
        "fecha": _iso(voucher.get("fecha_operacion")),
        "total": _texto_monto(voucher.get("total")),
        "moneda": voucher.get("moneda") or "PEN",
        "contraparte": contraparte.get("nombre") or "",
        "documento_contraparte": contraparte.get("documento") or "",
        "asociacion": voucher.get("asociacion"),
        "serie_numero": None,
        "periodo_comprobante": None,
    }


def _con_comprobante(pago: dict[str, Any], fila: dict[str, Any]) -> dict[str, Any]:
    pago["serie_numero"] = fila.get("serie_numero")
    pago["periodo_comprobante"] = fila.get("periodo")
    return pago


def _es_candidata(voucher: dict[str, Any], fila: dict[str, Any]) -> bool:
    if fila.get("libro") != voucher.get("libro"):
        return False
    if fila.get("tipo_cp") in _TIPOS_QUE_NO_SE_PAGAN:
        return False
    if (fila.get("moneda") or "PEN") != (voucher.get("moneda") or "PEN"):
        return False
    total_voucher, total_fila = _monto(voucher.get("total")), _monto(fila.get("total"))
    if total_voucher is None or total_fila is None:
        return False
    if not montos_iguales(total_voucher, total_fila):
        return False
    documento = normalizar_documento((voucher.get("contraparte") or {}).get("documento"))
    documento_fila = normalizar_documento(fila.get("documento_contraparte"))
    # Un Yape suele traer sólo el nombre: sin documento no hay con qué descartar.
    return not (documento and documento_fila and documento != documento_fila)


async def _filas(
    db, empresa_id: str, periodos: list[str], libro: str | None = None
) -> dict[Identidad, dict[str, Any]]:
    """Una fila por identidad. Si la de SUNAT y la externa coinciden un momento,
    gana la de SUNAT."""
    salida: dict[Identidad, dict[str, Any]] = {}
    for fila in await repo_comprobantes.candidatas_de_pago(db, empresa_id, periodos, libro):
        clave = identidad(fila)
        if clave not in salida or fila.get("origen") == "sire":
            salida[clave] = fila
    return salida


async def _retirar_filas_viejas(db, empresa_id: str, vouchers: list[dict[str, Any]]) -> None:
    """Antes, un voucher se copiaba como fila del periodo (tipo 00). Esa fila se
    borra, y el voucher queda como pago."""
    viejos = [v for v in vouchers if v.get("comprobante_id")]
    ids = [ObjectId(v["comprobante_id"]) for v in viejos if ObjectId.is_valid(v["comprobante_id"])]
    borradas = await repo_comprobantes.eliminar_externas(db, ids)
    for voucher in viejos:
        await repo_externos.marcar(db, voucher["_id"], ESTADO_INTEGRADO, None)
        voucher["comprobante_id"] = None
    if borradas:
        logger.info(
            "Filas de voucher retiradas del periodo empresa=%s borradas=%s", empresa_id, borradas
        )


async def _completar_periodo_de_pago_de(db, vouchers: list[dict[str, Any]]) -> None:
    for voucher in vouchers:
        pago_de = voucher.get("pago_de")
        if pago_de and not pago_de.get("periodo"):
            pago_de = {**pago_de, "periodo": voucher["periodo"]}
            await repo_externos.asociar(db, voucher["_id"], pago_de, voucher.get("asociacion"))
            voucher["pago_de"] = pago_de


async def asociar_automatico(db, empresa_id: str, periodo: str) -> int:
    """Asocia los vouchers del periodo sin comprobante que tienen una única
    candidata en su periodo o en el anterior."""
    vouchers = await repo_externos.vouchers_del_periodo(db, empresa_id, periodo)
    if not vouchers:
        return 0
    await _retirar_filas_viejas(db, empresa_id, vouchers)
    await _completar_periodo_de_pago_de(db, vouchers)
    periodos = periodos_que_puede_pagar(periodo)
    filas = await _filas(db, empresa_id, periodos)
    # Un comprobante ya pagado no se le asocia a otro voucher, sea del mes que
    # sea el que lo pagó.
    pagadores = {v["_id"]: v for v in await repo_externos.vouchers_que_pagan(
        db, empresa_id, periodos
    )}
    pagadores.update({v["_id"]: v for v in vouchers})
    ocupadas = {
        clave
        for v in pagadores.values()
        if (clave := _identidad_asociada(v)) is not None and clave in filas
    }

    asociados = 0
    for voucher in vouchers:
        if voucher.get("asociacion") == ASOCIACION_MANUAL:
            continue
        actual = _identidad_asociada(voucher)
        if actual is not None and actual in filas:
            continue
        candidatas = [
            fila
            for clave, fila in filas.items()
            if clave not in ocupadas and _es_candidata(voucher, fila)
        ]
        if len(candidatas) != 1:
            if actual is not None:
                # Apuntaba a un comprobante que ya no está.
                await repo_externos.asociar(db, voucher["_id"], None, None)
            continue
        elegida = candidatas[0]
        await repo_externos.asociar(db, voucher["_id"], _pago_de(elegida), ASOCIACION_AUTO)
        ocupadas.add(identidad(elegida))
        asociados += 1
    if asociados:
        logger.info(
            "Vouchers asociados empresa=%s periodo=%s asociados=%s",
            empresa_id, periodo, asociados,
        )
    return asociados


async def asociar_alrededor(db, empresa_id: str, periodo: str) -> int:
    """Después de que cambian los comprobantes de un periodo: sus vouchers y los
    del periodo siguiente, que también pueden pagarlos."""
    return await asociar_automatico(db, empresa_id, periodo) + await asociar_automatico(
        db, empresa_id, dominio_periodo.siguiente(periodo)
    )


async def integrar_voucher(db, empresa_id: str, voucher: dict[str, Any]) -> str:
    """Hace visible un voucher en su periodo, que ya existe, e intenta asociarlo."""
    await repo_externos.marcar(db, voucher["_id"], ESTADO_INTEGRADO, None)
    await asociar_automatico(db, empresa_id, voucher["periodo"])
    return ESTADO_INTEGRADO


async def asociar_manual(
    db,
    empresa_id: str,
    periodo: str,
    voucher_id: str,
    serie_numero: str | None,
    periodo_comprobante: str | None = None,
) -> dict[str, Any]:
    """Asocia un voucher a un comprobante de su periodo o del anterior, o lo
    desasocia con `None`.

    `periodo` es el de la pantalla desde la que se hace: el del voucher o el
    del comprobante que paga. Queda `manual` en los dos casos: la asociación
    automática ya no lo toca.
    """
    voucher = await repo_externos.obtener(db, empresa_id, voucher_id)
    actual = _identidad_asociada(voucher) if voucher else None
    if (
        not voucher
        or voucher.get("tipo_evidencia") != "voucher"
        or voucher.get("estado") != ESTADO_INTEGRADO
        or periodo not in (voucher.get("periodo"), actual[0] if actual else None)
    ):
        raise VoucherNoEncontrado(voucher_id)

    permitidos = periodos_que_puede_pagar(voucher["periodo"])
    pago_de = None
    fila = None
    if serie_numero:
        if periodo_comprobante is not None and periodo_comprobante not in permitidos:
            raise ComprobanteNoEncontrado(serie_numero)
        for candidato in [periodo_comprobante] if periodo_comprobante else permitidos:
            fila = await repo_comprobantes.obtener(
                db, empresa_id, candidato, serie_numero, Libro(voucher["libro"])
            )
            if fila:
                break
        if not fila:
            raise ComprobanteNoEncontrado(serie_numero)
        pago_de = _pago_de(fila)
    await repo_externos.asociar(db, voucher["_id"], pago_de, ASOCIACION_MANUAL)
    voucher.update(pago_de=pago_de, asociacion=ASOCIACION_MANUAL)
    pago = presentar(voucher)
    return _con_comprobante(pago, fila) if fila else pago


async def pagos_del_periodo(
    db, empresa_id: str, periodo: str, libro: str | None = None
) -> tuple[dict[Identidad, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Los pagos de cada comprobante del periodo, vengan de un voucher de este
    periodo o del siguiente, y los vouchers del periodo sin comprobante."""
    propios = await repo_externos.vouchers_del_periodo(db, empresa_id, periodo, libro)
    que_pagan = await repo_externos.vouchers_que_pagan(db, empresa_id, [periodo], libro)
    if not propios and not que_pagan:
        return {}, []
    filas = await _filas(db, empresa_id, periodos_que_puede_pagar(periodo), libro)

    por_comprobante: dict[Identidad, list[dict[str, Any]]] = {}
    vistos = set()
    for voucher in [*propios, *que_pagan]:
        clave = _identidad_asociada(voucher)
        if voucher["_id"] in vistos or clave is None or clave[0] != periodo or clave not in filas:
            continue
        vistos.add(voucher["_id"])
        por_comprobante.setdefault(clave, []).append(
            _con_comprobante(presentar(voucher), filas[clave])
        )
    sin_comprobante = [
        presentar(voucher)
        for voucher in propios
        if (clave := _identidad_asociada(voucher)) is None or clave not in filas
    ]
    return por_comprobante, sin_comprobante


async def adjuntar_pagos(
    db, empresa_id: str, periodo: str, datos: list[dict[str, Any]], libro: str | None = None
) -> list[dict[str, Any]]:
    """Agrega `pagos` a cada comprobante serializado. Devuelve los vouchers del
    periodo sin comprobante."""
    por_comprobante, sin_comprobante = await pagos_del_periodo(db, empresa_id, periodo, libro)
    for dato in datos:
        dato["pagos"] = por_comprobante.get(identidad(dato, periodo), [])
    return sin_comprobante


async def vouchers_con_candidatas(
    db, empresa_id: str, periodo: str, libro: str | None = None
) -> list[dict[str, Any]]:
    """Todos los vouchers del periodo, con su comprobante y las candidatas para
    asociarlo: las del mismo monto, en su periodo o en el anterior."""
    vouchers = await repo_externos.vouchers_del_periodo(db, empresa_id, periodo, libro)
    if not vouchers:
        return []
    filas = await _filas(db, empresa_id, periodos_que_puede_pagar(periodo), libro)
    salida = []
    for voucher in vouchers:
        pago = presentar(voucher)
        clave = _identidad_asociada(voucher)
        if clave is not None and clave in filas:
            _con_comprobante(pago, filas[clave])
        pago["candidatas"] = [
            {
                "periodo": fila.get("periodo"),
                "serie_numero": fila.get("serie_numero"),
                "razon_social": fila.get("razon_social") or "",
                "fecha_emision": _iso(fila.get("fecha_emision")),
                "total": _texto_monto(fila.get("total")),
                "moneda": fila.get("moneda") or "PEN",
            }
            for fila in filas.values()
            if _es_candidata(voucher, fila)
        ]
        salida.append(pago)
    return salida
