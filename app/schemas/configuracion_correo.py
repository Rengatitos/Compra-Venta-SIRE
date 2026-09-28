from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.domain.empresa import es_correo_valido


def _correo_opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = valor.strip()
    if valor and not es_correo_valido(valor):
        raise ValueError(f"«{valor}» no es un correo válido")
    return valor.lower()


class ConfiguracionCorreoUpdate(BaseModel):
    """Cambios parciales. `password` vacío o ausente conserva la guardada."""

    host: str | None = Field(None, max_length=255)
    puerto: int | None = Field(None, ge=1, le=65535)
    seguridad: Literal["starttls", "ssl", "ninguna"] | None = None
    usuario: str | None = Field(None, max_length=255)
    password: str | None = Field(None, max_length=512)
    remitente_nombre: str | None = Field(None, max_length=120)
    remitente_correo: str | None = None
    destinatarios_permitidos: list[str] | None = Field(None, max_length=100)
    max_adjunto_mb: int | None = Field(None, ge=1, le=25)
    dias_enlace: int | None = Field(None, ge=1, le=30)
    url_publica: str | None = Field(None, max_length=255)
    plantilla_asunto: str | None = Field(None, min_length=1, max_length=200)
    plantilla_cuerpo: str | None = Field(None, min_length=1, max_length=10000)

    @field_validator("host", "usuario", "remitente_nombre", mode="before")
    @classmethod
    def recortar(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("remitente_correo")
    @classmethod
    def validar_remitente(cls, v):
        return _correo_opcional(v)

    @field_validator("destinatarios_permitidos")
    @classmethod
    def validar_destinatarios(cls, v):
        if v is None:
            return None
        limpios: list[str] = []
        for correo in v:
            correo = _correo_opcional(correo)
            if correo and correo not in limpios:
                limpios.append(correo)
        return limpios

    @field_validator("url_publica")
    @classmethod
    def validar_url(cls, v):
        if v is None:
            return None
        v = v.strip().rstrip("/")
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("La URL pública debe empezar por http:// o https://")
        return v


class VariablePlantilla(BaseModel):
    nombre: str
    descripcion: str


class PlantillaResponse(BaseModel):
    asunto: str
    cuerpo: str


class ConfiguracionCorreoResponse(BaseModel):
    host: str
    puerto: int
    seguridad: str
    usuario: str
    # La contraseña nunca sale; solo si hay una guardada.
    password_configurada: bool
    remitente_nombre: str
    remitente_correo: str
    destinatarios_permitidos: list[str]
    max_adjunto_mb: int
    dias_enlace: int
    url_publica: str
    plantilla_asunto: str
    plantilla_cuerpo: str
    configurado: bool
    variables: list[VariablePlantilla]
    plantilla_por_defecto: PlantillaResponse


class VistaPreviaRequest(BaseModel):
    plantilla_asunto: str = Field(min_length=1, max_length=200)
    plantilla_cuerpo: str = Field(min_length=1, max_length=10000)


class VistaPreviaResponse(BaseModel):
    asunto: str
    texto: str
    html: str


class PruebaRequest(BaseModel):
    destinatario: str

    @field_validator("destinatario")
    @classmethod
    def validar(cls, v):
        correo = _correo_opcional(v)
        if not correo:
            raise ValueError("Indica a qué correo enviar la prueba")
        return correo
