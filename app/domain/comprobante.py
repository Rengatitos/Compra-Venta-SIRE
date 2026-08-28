from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.catalogos import DOC_IDENTIDAD_GENERICO


class Libro(str, Enum):
    VENTAS = "ventas"
    COMPRAS = "compras"


class Origen(str, Enum):
    SIRE = "sire"
    CONTASIS = "contasis"


class EstadoProcesamiento(str, Enum):
    SIRE_RECIBIDO = "sire_recibido"
    ANALIZADO = "analizado"
    ERROR_ANALISIS = "error_analisis"
    SIN_DATOS = "sin_datos"


# Comprobantes que el análisis con IA aún debe procesar.
ESTADOS_PENDIENTES_ANALISIS = frozenset(
    {EstadoProcesamiento.SIRE_RECIBIDO, EstadoProcesamiento.ERROR_ANALISIS}
)


CERO = Decimal("0.00")
TOLERANCIA_MONTO = Decimal("0.01")

_NO_ALNUM = re.compile(r"[^A-Z0-9]")
_SOLO_DIGITOS = re.compile(r"\D")
_VACIOS = frozenset({"", "-", "--", "NONE", "NULL", "#N/A", "N/A", "S/N"})


def _texto_crudo(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f")
    return str(valor).strip()


def _sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def _es_vacio(texto: str) -> bool:
    return texto.strip().upper() in _VACIOS


def normalizar_serie(valor: Any) -> str:
    texto = _texto_crudo(valor).upper()
    if _es_vacio(texto):
        return ""
    texto = _NO_ALNUM.sub("", _sin_tildes(texto))
    if not texto:
        return ""
    despojado = texto.lstrip("0")
    # Una serie enteramente de ceros colapsaría a cadena vacía.
    return despojado if despojado else "0"


def normalizar_numero(valor: Any) -> str:
    texto = _texto_crudo(valor).upper()
    if _es_vacio(texto):
        return ""
    texto = _NO_ALNUM.sub("", _sin_tildes(texto))
    if not texto:
        return ""
    if texto.isdigit():
        return str(int(texto))
    despojado = texto.lstrip("0")
    return despojado if despojado else "0"


def normalizar_documento(valor: Any) -> str:
    texto = _texto_crudo(valor).upper()
    if _es_vacio(texto):
        return ""
    return _SOLO_DIGITOS.sub("", texto)


def normalizar_tipo_cp(valor: Any) -> str:
    texto = _texto_crudo(valor).upper()
    if _es_vacio(texto):
        return ""
    texto = _NO_ALNUM.sub("", texto)
    if not texto:
        return ""
    if texto.isdigit():
        return texto.zfill(2)[-2:]
    return texto


def normalizar_razon_social(valor: Any) -> str:
    texto = _texto_crudo(valor).upper()
    if _es_vacio(texto):
        return ""
    return re.sub(r"\s+", " ", _sin_tildes(texto)).strip()


def normalizar_monto(valor: Any) -> Decimal:
    if isinstance(valor, Decimal):
        return valor.quantize(CERO, rounding=ROUND_HALF_UP)
    if isinstance(valor, bool):
        return CERO
    if isinstance(valor, (int, float)):
        return Decimal(str(valor)).quantize(CERO, rounding=ROUND_HALF_UP)

    texto = _texto_crudo(valor).replace(" ", "")
    if _es_vacio(texto):
        return CERO
    # Separadores de miles en cualquiera de los dos estilos: 1,234.56 / 1.234,56
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return Decimal(texto).quantize(CERO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return CERO


def normalizar_fecha(valor: Any) -> date | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = _texto_crudo(valor)
    if _es_vacio(texto):
        return None
    texto = texto.split("T")[0].split(" ")[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def montos_iguales(a: Decimal, b: Decimal, tolerancia: Decimal = TOLERANCIA_MONTO) -> bool:
    return abs(a - b) <= tolerancia


def es_contraparte_generica(documento: str) -> bool:
    return documento == "" or documento == DOC_IDENTIDAD_GENERICO


class ClaveComprobante(BaseModel):
    model_config = ConfigDict(frozen=True)

    tipo_cp: str
    serie: str
    numero: str

    def __str__(self) -> str:
        return f"{self.tipo_cp}-{self.serie}-{self.numero}"


class Comprobante(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    libro: Libro
    origen: Origen

    tipo_cp: str = ""
    serie: str = ""
    numero: str = ""
    tipo_doc_identidad: str = ""
    documento_contraparte: str = ""
    razon_social: str = ""

    fecha_emision: date | None = None
    fecha_vencimiento: date | None = None

    moneda: str = "PEN"
    tipo_cambio: Decimal | None = None

    base_imponible: Decimal = CERO
    igv: Decimal = CERO
    exonerado: Decimal = CERO
    inafecto: Decimal = CERO
    isc: Decimal = CERO
    otros_tributos: Decimal = CERO
    total: Decimal = CERO

    # Campos propios de cada origen que no entran al modelo común: el JSON
    # crudo del SIRE, el CAR SUNAT, la cuenta contable de Contasis, etc.
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tipo_cp", mode="before")
    @classmethod
    def _v_tipo_cp(cls, v: Any) -> str:
        return normalizar_tipo_cp(v)

    @field_validator("serie", mode="before")
    @classmethod
    def _v_serie(cls, v: Any) -> str:
        return normalizar_serie(v)

    @field_validator("numero", mode="before")
    @classmethod
    def _v_numero(cls, v: Any) -> str:
        return normalizar_numero(v)

    @field_validator("documento_contraparte", "tipo_doc_identidad", mode="before")
    @classmethod
    def _v_documento(cls, v: Any) -> str:
        return normalizar_documento(v)

    @field_validator("razon_social", mode="before")
    @classmethod
    def _v_razon(cls, v: Any) -> str:
        return normalizar_razon_social(v)

    @field_validator("fecha_emision", "fecha_vencimiento", mode="before")
    @classmethod
    def _v_fecha(cls, v: Any) -> date | None:
        return normalizar_fecha(v)

    @field_validator(
        "base_imponible",
        "igv",
        "exonerado",
        "inafecto",
        "isc",
        "otros_tributos",
        "total",
        mode="before",
    )
    @classmethod
    def _v_monto(cls, v: Any) -> Decimal:
        return normalizar_monto(v)

    @field_validator("moneda", mode="before")
    @classmethod
    def _v_moneda(cls, v: Any) -> str:
        texto = _texto_crudo(v).upper()
        return texto if texto else "PEN"

    @property
    def clave(self) -> ClaveComprobante:
        return ClaveComprobante(tipo_cp=self.tipo_cp, serie=self.serie, numero=self.numero)

    @property
    def serie_numero(self) -> str:
        return f"{self.serie}-{self.numero}"

    @property
    def es_valido(self) -> bool:
        return bool(self.serie and self.numero and self.fecha_emision)
