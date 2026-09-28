
from pydantic import BaseModel, Field, field_validator

from app.domain.carga_empresas import es_ruc_valido
from app.domain.empresa import normalizar_correos
from app.schemas.generic import FechaUtc
from app.services.sunat.ficha_ruc import FichaRuc


class ActividadEconomica(BaseModel):
    """Actividad de la ficha RUC. La usa el clasificador contable como contexto."""

    tipo: str | None = None  # PRINCIPAL / SECUNDARIA según SUNAT
    ciiu: str
    descripcion: str | None = None
    # `sunat` (de la ficha RUC) o `manual` (agregada en Ajustes). Al volver a
    # consultar SUNAT solo se reemplazan las de `sunat`.
    origen: str | None = None

    @field_validator("ciiu")
    @classmethod
    def validar_ciiu(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("El CIIU debe ser numérico")
        return v


class EmpresaBase(BaseModel):
    ruc: str

    @field_validator("ruc")
    @classmethod
    def validar_ruc(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit() or len(v) != 11:
            raise ValueError("El RUC debe tener 11 dígitos")
        return v


class EmpresaCreate(EmpresaBase):
    usuario: str = Field(min_length=1)
    password: str = Field(min_length=1)
    nombre: str | None = None
    sunat_client_id: str | None = None
    sunat_client_secret: str | None = None

    @field_validator("ruc")
    @classmethod
    def validar_digito(cls, v: str) -> str:
        # Solo al registrar: las empresas que ya existen se siguen leyendo
        # aunque su RUC no pase la regla (datos de prueba, altas antiguas).
        if not es_ruc_valido(v):
            raise ValueError("RUC inválido: revisa el dígito verificador")
        return v

    # Antes de validar, para que un usuario de solo espacios no pase el mínimo.
    @field_validator("usuario", "nombre", "sunat_client_id", "sunat_client_secret", mode="before")
    @classmethod
    def recortar(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v


class EmpresaUpdate(BaseModel):
    nombre: str | None = None
    usuario: str | None = None
    password: str | None = None
    sunat_token: str | None = None
    sunat_client_id: str | None = None
    sunat_client_secret: str | None = None
    actividades_economicas: list[ActividadEconomica] | None = None
    # CIIU que manda al clasificar (p. ej. el restaurante aunque SUNAT diga
    # otra cosa). Debe estar entre `actividades_economicas`.
    ciiu_principal_clasificacion: str | None = None
    # A quién se envían los resultados de esta empresa. `None` = no tocar la
    # lista; `[]` = vaciarla.
    correos_notificacion: list[str] | None = None

    @field_validator("correos_notificacion")
    @classmethod
    def validar_correos(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else normalizar_correos(v)


class RegistroEmpresa(BaseModel):
    """Quién dio de alta la empresa, cuándo y cómo."""

    modalidad: str
    por: str
    fecha: FechaUtc | None = None
    carga_id: str | None = None


class EmpresaResponse(EmpresaBase):
    id: str = Field(validation_alias="_id")
    nombre: str | None = None
    usuario: str
    fecha_creacion: str | None = None
    rubro: str | None = None
    ciiu: str | None = None
    registro: RegistroEmpresa | None = None
    correos_notificacion: list[str] = []
    actividades_economicas: list[ActividadEconomica] = []
    ciiu_principal_clasificacion: str | None = None
    # Última ficha RUC consultada en SUNAT (`POST /empresas/{ruc}/ficha-ruc`).
    ficha_ruc: FichaRuc | None = None

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id(cls, v):
        return str(v)

    model_config = {"from_attributes": True, "populate_by_name": True}


class EmpresaCreada(EmpresaResponse):
    """Respuesta del alta individual: la carga sigue el resto en segundo plano."""

    carga_id: str
