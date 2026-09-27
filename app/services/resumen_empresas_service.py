"""Resumen de todas las empresas para el panel general (`GET /empresas/resumen`).

Tres consultas en total, sea cual sea el número de empresas: las empresas, sus
periodos (un `$in`) y un agregado de `jobs` por RUC.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.domain.jobs import EstadoJob
from app.repositories import empresas as repo_empresas
from app.repositories import jobs as repo_jobs
from app.repositories import periodos as repo_periodos
from app.services import jobs_service

# Los procesos terminados se cuentan dentro de esta ventana; los vivos, todos.
DIAS = 30
MAX_EMPRESAS = 1000


def _ceros() -> dict[str, int]:
    return {estado.value: 0 for estado in EstadoJob}


async def resumir(db) -> dict[str, Any]:
    desde = datetime.now(UTC) - timedelta(days=DIAS)
    empresas, por_ruc = await asyncio.gather(
        repo_empresas.listar(db, limit=MAX_EMPRESAS),
        repo_jobs.resumen_por_ruc(db, desde),
    )
    periodos = await repo_periodos.listar_por_empresas(db, [str(e["_id"]) for e in empresas])

    totales = _ceros()
    filas = []
    for empresa in empresas:
        jobs = por_ruc.get(empresa["ruc"]) or {}
        conteo = jobs.get("procesos_por_estado") or _ceros()
        for estado, cantidad in conteo.items():
            totales[estado] += cantidad
        suyos = periodos.get(str(empresa["_id"]), [])
        ultimo = jobs.get("ultimo")
        filas.append({
            "ruc": empresa["ruc"],
            "nombre": empresa.get("nombre"),
            "correos_notificacion": empresa.get("correos_notificacion") or [],
            "total_periodos": len(suyos),
            "periodos": suyos,
            "ultima_actualizacion_sire": jobs.get("ultima_actualizacion_sire"),
            "ultimo_proceso": jobs_service.serializar(ultimo) if ultimo else None,
            "procesos_por_estado": conteo,
        })

    filas.sort(key=lambda f: ((f["nombre"] or "").lower() or f["ruc"], f["ruc"]))
    return {
        "total_empresas": len(filas),
        "dias": DIAS,
        "procesos_por_estado": totales,
        "empresas": filas,
    }
