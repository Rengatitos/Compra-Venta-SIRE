"""Configuración del correo de fin de solicitud y su plantilla.

Vive en Mongo y se edita desde el panel (`/correos`), no en variables de
entorno: el servidor SMTP, el remitente, la lista blanca de destinatarios y el
texto del mensaje.

La plantilla es texto con variables `{{nombre}}`. La sustitución es literal
—nada de Jinja—, así que un texto con llaves no ejecuta nada, y una variable
que no existe se deja tal cual para que se vea el error al previsualizar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from html import escape
from typing import Any

SEGURIDADES = ("starttls", "ssl", "ninguna")

# Variable → qué pone. Es lo que el panel lista junto a la plantilla.
VARIABLES: dict[str, str] = {
    "destinatario": "Correo de quien recibe el mensaje",
    "resumen": "Cuántas empresas y periodos incluye, p. ej. «2 empresas, 3 periodos»",
    "empresas": "Nombres de las empresas incluidas, separados por comas",
    "periodos": "Periodos incluidos, p. ej. «07/2026, 08/2026»",
    "fecha": "Día en que terminó el procesamiento",
    "etapas": "Estado de cada etapa: SIRE, comprobantes, IA y archivos finales",
    "resultados": "Tabla con el estado de cada empresa y periodo",
    "entrega": "Cómo se entrega el ZIP: adjunto o enlace de descarga",
}

ASUNTO_POR_DEFECTO = "Sire · Procesamiento terminado: {{resumen}}"
CUERPO_POR_DEFECTO = """Hola,

El procesamiento que pediste en Sire ha terminado ({{fecha}}).

{{etapas}}

{{resultados}}

{{entrega}}
"""

_VARIABLE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class ConfiguracionCorreo:
    host: str = ""
    puerto: int = 587
    seguridad: str = "starttls"
    usuario: str = ""
    # Cifrada con la misma clave que las contraseñas SOL; nunca sale por la API.
    password_cifrada: str = ""
    remitente_nombre: str = "Sire"
    remitente_correo: str = ""
    # Vacía = se puede escribir a cualquiera.
    destinatarios_permitidos: list[str] = field(default_factory=list)
    max_adjunto_mb: int = 18
    dias_enlace: int = 7
    url_publica: str = ""
    plantilla_asunto: str = ASUNTO_POR_DEFECTO
    plantilla_cuerpo: str = CUERPO_POR_DEFECTO

    @property
    def configurado(self) -> bool:
        return bool(self.host)

    @property
    def remitente(self) -> str:
        correo = self.remitente_correo or self.usuario
        return f"{self.remitente_nombre} <{correo}>" if self.remitente_nombre and correo else correo

    def permitido(self, correo: str) -> bool:
        lista = self.destinatarios_permitidos
        return not lista or correo.lower() in lista


CAMPOS = tuple(ConfiguracionCorreo.__dataclass_fields__)


def desde_documento(documento: dict[str, Any] | None) -> ConfiguracionCorreo:
    base = ConfiguracionCorreo()
    if not documento:
        return base
    return replace(base, **{c: documento[c] for c in CAMPOS if documento.get(c) is not None})


@dataclass(frozen=True)
class Valor:
    """Lo que pone una variable, en texto plano y en HTML."""

    texto: str
    html: str | None = None


def renderizar_texto(plantilla: str, valores: dict[str, Valor]) -> str:
    def sustituir(m: re.Match[str]) -> str:
        valor = valores.get(m.group(1))
        return valor.texto if valor else m.group(0)

    return _VARIABLE.sub(sustituir, plantilla)


def renderizar_html(plantilla: str, valores: dict[str, Valor]) -> str:
    """El texto de la plantilla se escapa y sus saltos de línea se respetan; las
    variables con HTML propio (la tabla, la lista de etapas) entran tal cual."""
    partes: list[str] = []
    posicion = 0
    for m in _VARIABLE.finditer(plantilla):
        partes.append(_texto_a_html(plantilla[posicion:m.start()]))
        valor = valores.get(m.group(1))
        if valor is None:
            partes.append(escape(m.group(0)))
        else:
            partes.append(valor.html if valor.html is not None else _texto_a_html(valor.texto))
        posicion = m.end()
    partes.append(_texto_a_html(plantilla[posicion:]))
    return "".join(partes)


def _texto_a_html(texto: str) -> str:
    return escape(texto).replace("\n", "<br>\n")
