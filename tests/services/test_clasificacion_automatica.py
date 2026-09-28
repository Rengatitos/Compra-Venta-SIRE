"""Clasificación sin intervención: qué se manda a la IA, reintentos por
comprobante y error persistente (sección 7 de los requerimientos)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.services import clasificacion_service as servicio
from app.services.cola.errores import ErrorTransitorio


def test_no_se_vuelven_a_mandar_los_que_ya_tienen_codigo_ni_los_persistentes():
    filtro = repo_comprobantes._filtro_para_clasificar("e1", "202608", Libro.COMPRAS, False)

    assert filtro["clasificacion_estado"] == {"$ne": "error_persistente"}
    assert {"clasificacion_contable": {"$exists": False}} in filtro["$or"]
    assert {"clasificacion_contable.requiere_revision": True} in filtro["$or"]
    assert {"clasificacion_contable.cuenta_base.codigo": {"$in": [None, ""]}} in filtro["$or"]


def test_reclasificar_toma_todos():
    filtro = repo_comprobantes._filtro_para_clasificar("e1", "202608", Libro.COMPRAS, True)
    assert "$or" not in filtro
    assert "clasificacion_estado" not in filtro


@pytest.mark.parametrize(
    ("clasificacion", "valido"),
    [
        ({"requiere_revision": False, "cuenta_base": {"codigo": "6011"}}, True),
        ({"requiere_revision": True, "cuenta_base": {"codigo": "6011"}}, False),
        ({"requiere_revision": False, "cuenta_base": None}, False),
        ({"requiere_revision": False, "cuenta_base": {"codigo": "12345678901"}}, False),
        (None, False),
    ],
)
def test_codigo_valido_es_el_que_llega_al_excel(clasificacion, valido):
    assert servicio.tiene_codigo_valido(clasificacion) is valido


@pytest.fixture
def intentos(monkeypatch):
    registrados = []

    async def registrar(db, documento_id, estado, *, intentos, error=None):
        registrados.append((documento_id, estado, intentos, error))

    monkeypatch.setattr(servicio.repo_comprobantes, "registrar_intento_clasificacion", registrar)
    monkeypatch.setattr(servicio.settings, "CLASIFICADOR_MAX_INTENTOS_COMPROBANTE", 3)
    return registrados


def test_cada_intento_sin_codigo_suma_y_al_tope_queda_como_error_persistente(intentos):
    sin_cuenta = {"requiere_revision": True, "cuenta_base": None}

    primero = asyncio.run(servicio._registrar_intento(
        None, {"_id": 1, "clasificacion_intentos": 0}, resultado=sin_cuenta
    ))
    ultimo = asyncio.run(servicio._registrar_intento(
        None, {"_id": 1, "clasificacion_intentos": 2}, error="GEMINI_API_ERROR: 503"
    ))
    acierto = asyncio.run(servicio._registrar_intento(
        None, {"_id": 2, "clasificacion_intentos": 1},
        resultado={"requiere_revision": False, "cuenta_base": {"codigo": "6011"}},
    ))

    assert primero == "sin_codigo"
    assert ultimo == "error_persistente"
    assert acierto == "clasificado"
    assert intentos[1] == (1, "error_persistente", 3, "GEMINI_API_ERROR: 503")
    assert intentos[2][2] == 1  # acertar no gasta un intento


def resultado(**campos):
    base = {
        "clasificados": 0, "reutilizados": 0, "propagados": 0, "requieren_revision": 0,
        "sin_descripcion": 0, "errores": 0, "errores_persistentes": 0, "reintentables": 0,
        "sin_glosa_omitidos": 0, "contrapartes_con_ciiu": 0, "pendientes_restantes": 0,
        "restantes_por_tope": 0, "detalle_errores": [],
    }
    return {**base, **campos}


def test_sigue_por_rondas_mientras_el_tope_deje_comprobantes(monkeypatch):
    lotes = AsyncMock(side_effect=[
        resultado(clasificados=200, restantes_por_tope=50),
        resultado(clasificados=50),
    ])
    monkeypatch.setattr(servicio, "clasificar_periodo", lotes)

    final = asyncio.run(servicio.clasificar_hasta_terminar(
        None, {}, "202608", Libro.COMPRAS, AsyncMock(), ultimo_intento=False
    ))

    assert lotes.await_count == 2
    assert final["clasificados"] == 250
    assert final["rondas"] == 2


def test_si_quedan_reintentables_pide_otro_intento_a_la_cola(monkeypatch):
    monkeypatch.setattr(
        servicio, "clasificar_periodo",
        AsyncMock(return_value=resultado(clasificados=10, errores=2, reintentables=2)),
    )
    with pytest.raises(ErrorTransitorio):
        asyncio.run(servicio.clasificar_hasta_terminar(
            None, {}, "202608", Libro.COMPRAS, AsyncMock(), ultimo_intento=False
        ))


def test_en_el_ultimo_intento_devuelve_lo_conseguido(monkeypatch):
    monkeypatch.setattr(
        servicio, "clasificar_periodo",
        AsyncMock(return_value=resultado(clasificados=10, reintentables=2)),
    )
    final = asyncio.run(servicio.clasificar_hasta_terminar(
        None, {}, "202608", Libro.COMPRAS, AsyncMock(), ultimo_intento=True
    ))
    assert final["reintentables"] == 2
