"""Quién puede entrar al panel.

La autorización del panel es una lista de correos en el entorno
(`GOOGLE_ALLOWED_EMAILS`), no una colección de Mongo: hoy hay un solo usuario y
una tabla entera para eso sería estructura sin contenido. Aquí vive la única
regla de decisión, como función pura, para poder probarla sin FastAPI, sin red
y sin base de datos.
"""

from __future__ import annotations


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
