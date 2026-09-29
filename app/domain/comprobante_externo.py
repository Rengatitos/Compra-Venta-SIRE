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
    # se identifica por su número de operación y va con tipo_cp "00".
    VOUCHER = "voucher"
    COMPROBANTE = "comprobante"


# `recibido`: todavía no entra a su periodo (no existe o falta refrescar). Un
# voucher se queda así para siempre: no pasa al periodo.
# `integrado`: se copió como fila del periodo (`comprobante_id` la apunta).
# `ya_existia`: el periodo ya tenía ese comprobante, o la propuesta SUNAT lo
# trajo después y reemplazó a la fila externa.
ESTADO_RECIBIDO = "recibido"
ESTADO_INTEGRADO = "integrado"
ESTADO_YA_EXISTIA = "ya_existia"


def va_al_periodo(externo: dict) -> bool:
    """Sólo los comprobantes pasan al periodo; un voucher se queda en Externos."""
    return externo.get("tipo_evidencia") != TipoEvidencia.VOUCHER.value


def periodo_de(fecha: date) -> str:
    return validar(f"{fecha.year:04d}{fecha.month:02d}")
