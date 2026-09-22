"""Vinculación de un dispositivo de sire-bot con una empresa mediante un código de 6 dígitos.

El panel genera el código (sesión de usuario) y la persona lo escribe en el bot;
el bot lo canjea con su `X-Api-Key`. El código vive 10 minutos, sirve una vez y
solo vale el último generado para cada empresa.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from app.repositories import codigos_vinculacion as repo_codigos

VIGENCIA = timedelta(minutes=10)
INTENTOS_GENERACION = 5


class CodigoInvalido(Exception):
    """No existe, venció o no tiene el formato de 6 dígitos."""


class CodigoYaUsado(Exception):
    pass


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


def _iso(fecha: datetime) -> str:
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC).isoformat().replace("+00:00", "Z")


def nombre_de(empresa: dict) -> str:
    return (empresa.get("nombre") or "").strip() or f"RUC {empresa['ruc']}"


async def generar(db, empresa: dict, creado_por: str, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(UTC)
    await repo_codigos.invalidar_activos(db, empresa["ruc"])

    expira_en = ahora + VIGENCIA
    for _ in range(INTENTOS_GENERACION):
        codigo = f"{secrets.randbelow(1_000_000):06d}"
        try:
            await repo_codigos.crear(
                db,
                {
                    "empresa_id": str(empresa["_id"]),
                    "ruc": empresa["ruc"],
                    "codigo_hash": hash_codigo(codigo),
                    "creado_en": ahora,
                    "expira_en": expira_en,
                    "creado_por": creado_por,
                    "usado_en": None,
                    "dispositivo_id": None,
                },
            )
        except DuplicateKeyError:
            # Choca con un código ya canjeado que aún no venció: probar otro.
            continue
        return {"codigo": codigo, "expira_en": _iso(expira_en)}

    raise RuntimeError("No se pudo generar un código de vinculación único")


async def canjear(
    db, empresa: dict, codigo: str, dispositivo_id: str, ahora: datetime | None = None
) -> dict:
    ahora = ahora or datetime.now(UTC)
    codigo = (codigo or "").strip()
    if len(codigo) != 6 or not codigo.isdigit():
        raise CodigoInvalido

    codigo_hash = hash_codigo(codigo)
    canjeado = await repo_codigos.canjear(db, empresa["ruc"], codigo_hash, dispositivo_id, ahora)
    if canjeado is None:
        existente = await repo_codigos.buscar(db, empresa["ruc"], codigo_hash)
        if existente and existente.get("usado_en") is not None:
            raise CodigoYaUsado
        raise CodigoInvalido

    return {"empresa": {"ruc": empresa["ruc"], "nombre": nombre_de(empresa)}}
