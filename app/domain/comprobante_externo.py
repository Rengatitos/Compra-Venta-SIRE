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


ESTADO_RECIBIDO = "recibido"


def periodo_de(fecha: date) -> str:
    return validar(f"{fecha.year:04d}{fecha.month:02d}")
