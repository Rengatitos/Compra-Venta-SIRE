from __future__ import annotations

from datetime import date
from enum import Enum

from app.domain.periodo import validar


class Fuente(str, Enum):
    """De dónde sacó el bot el comprobante (la foto que le mandaron)."""

    YAPE = "yape"
    PLIN = "plin"
    MERCADO_PAGO = "mercado_pago"
    NIUBIZ = "niubiz"
    BOLETA = "boleta"
    FACTURA = "factura"
    OTRO = "otro"


class TipoEvidencia(str, Enum):
    # Un voucher de pago no es un comprobante de SUNAT: no tiene serie ni número,
    # se identifica por su número de operación y va con tipo_cp "00". No es una
    # fila del periodo sino el pago de una: ver `app.services.pagos_vouchers`.
    VOUCHER = "voucher"
    COMPROBANTE = "comprobante"


# `recibido`: todavía no entra a su periodo (no existe o falta refrescar).
# `integrado`: un comprobante se copió como fila del periodo (`comprobante_id`
# la apunta); un voucher ya se ve en el periodo, asociado o no (`pago_de`).
# `ya_existia`: el periodo ya tenía ese comprobante, o la propuesta SUNAT lo
# trajo después y reemplazó a la fila externa. No aplica a vouchers.
ESTADO_RECIBIDO = "recibido"
ESTADO_INTEGRADO = "integrado"
ESTADO_YA_EXISTIA = "ya_existia"

# Cómo quedó asociado un voucher al comprobante que paga. `manual` también
# vale para uno que el usuario desasoció: la asociación automática no lo toca.
ASOCIACION_AUTO = "auto"
ASOCIACION_MANUAL = "manual"

# Código de la Tabla 1 de SUNAT (`catalogos.MEDIOS_DE_PAGO`) de cada fuente.
# Yape y Plin son transferencias entre cuentas; de Mercado Pago y Niubiz no se
# sabe si fue tarjeta de débito o de crédito. Pendiente de confirmar con el
# contador.
MEDIO_PAGO_POR_FUENTE: dict[str, str] = {
    Fuente.YAPE.value: "003",
    Fuente.PLIN.value: "003",
    Fuente.MERCADO_PAGO.value: "999",
    Fuente.NIUBIZ.value: "999",
}

NOMBRE_FUENTE: dict[str, str] = {
    Fuente.YAPE.value: "Yape",
    Fuente.PLIN.value: "Plin",
    Fuente.MERCADO_PAGO.value: "Mercado Pago",
    Fuente.NIUBIZ.value: "Niubiz",
}


def es_voucher(externo: dict) -> bool:
    return externo.get("tipo_evidencia") == TipoEvidencia.VOUCHER.value


def periodo_de(fecha: date) -> str:
    return validar(f"{fecha.year:04d}{fecha.month:02d}")
