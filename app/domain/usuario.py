"""Quién puede entrar al panel y con qué rol.

Hay dos fuentes de acceso:

- `GOOGLE_ALLOWED_EMAILS`, en el entorno: los **administradores fijos**. Son
  admins siempre y no se pueden quitar desde el panel, así que ningún error
  desde la web deja el sistema sin nadie que pueda entrar a arreglarlo.
- La colección `usuarios` de Mongo: los correos que un administrador agrega
  desde el panel, cada uno con rol `admin` o `usuario`.

Aquí vive la regla de decisión, como función pura, para poder probarla sin
FastAPI, sin red y sin base de datos.
"""

from __future__ import annotations

from enum import Enum


class Rol(str, Enum):
    ADMIN = "admin"  # entra y además gestiona quién tiene acceso
    USUARIO = "usuario"  # entra y trabaja, sin gestionar accesos


def normalizar_correo(valor: str | None) -> str:
    """Forma canónica de un correo: sin espacios alrededor y en minúsculas.

    Google entrega el correo ya en minúsculas, pero la allowlist la escribe una
    persona en un `.env`, así que se normalizan los dos lados antes de comparar.
    """
    return (valor or "").strip().lower()


def esta_permitido(correo: str | None, permitidos: list[str]) -> bool:
    """Si ese correo puede entrar al panel.

    Una lista vacía deja fuera a todo el mundo. Es el fallo seguro: si la
    variable no llegó al despliegue, es preferible que no entre nadie a que
    entre cualquier cuenta de Google.
    """
    normalizado = normalizar_correo(correo)
    if not normalizado:
        return False
    return normalizado in {normalizar_correo(p) for p in permitidos}


def resolver_rol(correo: str | None, fijos: list[str], rol_registrado: str | None) -> Rol | None:
    """El rol con el que entra ese correo, o `None` si no tiene acceso.

    `rol_registrado` es el que tiene en la colección `usuarios`, si está. Un
    administrador fijo es admin aunque en la colección figure como usuario.
    """
    if esta_permitido(correo, fijos):
        return Rol.ADMIN
    if not normalizar_correo(correo) or rol_registrado is None:
        return None
    try:
        return Rol(rol_registrado)
    except ValueError:
        return None
