"""El avance de la extracción nace en el hilo de Playwright y tiene que llegar
al job, que vive en el loop. Es el punto donde antes se perdía: el trabajo se
pasaba minutos en `0 / N` y no había forma de distinguirlo de uno colgado."""

from __future__ import annotations

import asyncio

from app.services import detalle_service

EMPRESA = {"_id": "abc123", "ruc": "20608997106"}
PENDIENTES = [
    {"serie_numero": "F001-1"},
    {"serie_numero": "F001-2"},
    {"serie_numero": "F001-3"},
]


def _correr(monkeypatch, pendientes):
    """Ejecuta `extraer` con el repositorio y el scraping simulados."""
    reportes: list[tuple[int, int, str]] = []

    async def reportar(actual: int, total: int, mensaje: str = "") -> None:
        reportes.append((actual, total, mensaje))

    async def listar_sin_detalle(db, empresa_id, periodo):
        return pendientes

    async def guardar_detalle_sunat(db, empresa_id, periodo, serie_numero, detalle):
        return None

    async def obtener_detalles(empresa, comprobantes, progreso=None, **resto):
        # Igual que Playwright: el recorrido ocurre fuera del loop.
        def en_otro_hilo():
            for hechos, comprobante in enumerate(comprobantes):
                if progreso:
                    progreso(hechos, comprobante["serie_numero"])
            return {c["serie_numero"]: [{"descripcion": "un ítem"}] for c in comprobantes}

        return await asyncio.to_thread(en_otro_hilo)

    monkeypatch.setattr(
        detalle_service.repo_comprobantes, "listar_sin_detalle", listar_sin_detalle
    )
    monkeypatch.setattr(
        detalle_service.repo_comprobantes, "guardar_detalle_sunat", guardar_detalle_sunat
    )
    monkeypatch.setattr(detalle_service.scraping_sunat, "obtener_detalles", obtener_detalles)

    async def principal():
        resultado = await detalle_service.extraer(None, EMPRESA, "202606", reportar)
        # Los avisos del hilo se agendan sin esperarlos: se les da un turno de
        # loop para que se vacíen antes de mirar la lista.
        await asyncio.sleep(0)
        return resultado

    return asyncio.run(principal()), reportes


def test_reporta_el_avance_de_cada_comprobante(monkeypatch):
    resultado, reportes = _correr(monkeypatch, PENDIENTES)

    assert resultado == {"procesados": 3, "con_detalle": 3}

    # Uno por comprobante, además del inicial y el final.
    intermedios = [r for r in reportes if r[2].startswith("Extrayendo F001-")]
    assert [(actual, total) for actual, total, _ in intermedios] == [(0, 3), (1, 3), (2, 3)]
    assert intermedios[0][2] == "Extrayendo F001-1 (1 de 3)"

    assert reportes[0] == (0, 3, "Extrayendo detalle de 3 comprobantes")
    assert reportes[-1] == (3, 3, "Extracción finalizada")


def test_sin_pendientes_no_abre_el_navegador(monkeypatch):
    resultado, reportes = _correr(monkeypatch, [])

    assert resultado == {"procesados": 0, "con_detalle": 0}
    assert reportes == [(0, 0, "No hay comprobantes pendientes de detalle")]
