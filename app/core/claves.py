"""Contraseñas de las cuentas de API: se generan aquí y solo se guarda su hash.

scrypt de la biblioteca estándar, con sal aleatoria por contraseña. El formato
guardado lleva sus parámetros (`scrypt$n$r$p$sal$hash`) para poder endurecerlos
más adelante sin invalidar las que ya existen.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

N, R, P, LARGO = 2**14, 8, 1, 32


def generar() -> str:
    """Contraseña nueva: 32 caracteres URL-safe (~190 bits)."""
    return secrets.token_urlsafe(24)


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode()


def hashear(clave: str) -> str:
    sal = secrets.token_bytes(16)
    derivada = hashlib.scrypt(clave.encode(), salt=sal, n=N, r=R, p=P, dklen=LARGO)
    return f"scrypt${N}${R}${P}${_b64(sal)}${_b64(derivada)}"


def verificar(clave: str, guardado: str) -> bool:
    try:
        esquema, n, r, p, sal, esperado = guardado.split("$")
        if esquema != "scrypt":
            return False
        esperado_b = base64.b64decode(esperado)
        derivada = hashlib.scrypt(
            clave.encode(),
            salt=base64.b64decode(sal),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(esperado_b),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derivada, esperado_b)
