"""Resumen de todas las empresas para el panel general (`GET /empresas/resumen`).

Tres consultas en total, sea cual sea el número de empresas: las empresas, sus
periodos (un `$in`) y un agregado de `jobs` por RUC.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.carga_empresas import EstadoFila, Motivo
from app.domain.jobs import EstadoJob
from app.repositories import cargas_empresas as repo_cargas
from app.repositories import empresas as repo_empresas
from app.repositories import jobs as repo_jobs
from app.repositories import periodos as repo_periodos
from app.services import jobs_service

# Los procesos terminados se cuentan dentro de esta ventana; los vivos, todos.
DIAS = 30
MAX_EMPRESAS = 1000


SIN_CREDENCIALES = (
    "No tiene las credenciales del API SUNAT: revisa su RUC, usuario y clave SOL y "
    "vuelve a intentarlo."
)


def _ceros() -> dict[str, int]:
    return {estado.value: 0 for estado in EstadoJob}


def estado_alta(empresa: dict[str, Any], fila: dict[str, Any] | None) -> tuple[str, str | None]:
    """`lista`, `registrando` (la cola aún completa su alta) o
    `requiere_correccion`, con el motivo. Sin client_id/secret la empresa no
    puede descargar el SIRE, así que no se deja entrar en ella."""
    if empresa.get("sunat_client_id") and empresa.get("sunat_client_secret"):
        return "lista", None
    if fila and fila.get("estado") == EstadoFila.PENDIENTE.value:
        return "registrando", None
    motivos = [
        m for m in (fila or {}).get("motivos") or []
        if not m.startswith(Motivo.EN_PROCESO.value)
    ]
    return "requiere_correccion", " · ".join(motivos) or SIN_CREDENCIALES


async def resumir(db) -> dict[str, Any]:
    desde = datetime.now(UTC) - timedelta(days=DIAS)
    empresas, por_ruc = await asyncio.gather(
        repo_empresas.listar(db, limit=MAX_EMPRESAS),
        repo_jobs.resumen_por_ruc(db, desde),
    )
    periodos, filas_alta = await asyncio.gather(
        repo_periodos.listar_por_empresas(db, [str(e["_id"]) for e in empresas]),
        repo_cargas.ultima_fila_por_ruc(db, [e["ruc"] for e in empresas]),
    )

    totales = _ceros()
    filas = []
    for empresa in empresas:
        jobs = por_ruc.get(empresa["ruc"]) or {}
        conteo = jobs.get("procesos_por_estado") or _ceros()
        for estado, cantidad in conteo.items():
            totales[estado] += cantidad
        suyos = periodos.get(str(empresa["_id"]), [])
        ultimo = jobs.get("ultimo")
        alta, motivo = estado_alta(empresa, filas_alta.get(empresa["ruc"]))
        filas.append({
            "ruc": empresa["ruc"],
            "nombre": empresa.get("nombre"),
            "correos_notificacion": empresa.get("correos_notificacion") or [],
            "total_periodos": len(suyos),
            "periodos": suyos,
            "ultima_actualizacion_sire": jobs.get("ultima_actualizacion_sire"),
            "ultimo_proceso": jobs_service.serializar(ultimo) if ultimo else None,
            "procesos_por_estado": conteo,
            "estado_alta": alta,
            "motivo_alta": motivo,
        })

    filas.sort(key=lambda f: ((f["nombre"] or "").lower() or f["ruc"], f["ruc"]))
    return {
        "total_empresas": len(filas),
        "dias": DIAS,
        "procesos_por_estado": totales,
        "empresas": filas,
    }
