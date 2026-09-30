from pydantic import BaseModel, Field


class PagoVoucher(BaseModel):
    """Un voucher de Apaclla Bot como pago de un comprobante del periodo."""

    id: str
    # El del voucher, por su fecha.
    periodo: str
    libro: str
    fuente: str
    # Nombre para mostrar (Yape, Plin...) y código de la Tabla 1 de SUNAT.
    medio_pago: str
    codigo_medio_pago: str
    nro_operacion: str
    fecha: str | None = None
    total: str | None = None
    moneda: str = "PEN"
    contraparte: str = ""
    documento_contraparte: str = ""
    # `auto` o `manual`; `None` mientras nunca se asoció.
    asociacion: str | None = None
    # El comprobante que paga, de este periodo o del anterior; `None` si está
    # sin comprobante.
    serie_numero: str | None = None
    periodo_comprobante: str | None = None


class CandidataVoucher(BaseModel):
    periodo: str
    serie_numero: str
    razon_social: str = ""
    fecha_emision: str | None = None
    total: str | None = None
    moneda: str = "PEN"


class VoucherPeriodo(PagoVoucher):
    # Comprobantes del mismo libro, moneda y monto que podría pagar, en su
    # periodo o en el anterior.
    candidatas: list[CandidataVoucher] = []


class AsociacionVoucher(BaseModel):
    # `None` desasocia.
    serie_numero: str | None = Field(None, min_length=1)
    # Periodo del comprobante: el del voucher o el anterior. Sin él se busca
    # primero en el del voucher.
    periodo: str | None = Field(None, pattern=r"^20\d{2}(0[1-9]|1[0-2])$")
