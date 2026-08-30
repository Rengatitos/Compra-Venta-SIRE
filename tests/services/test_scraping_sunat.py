"""`obtener_detalles` pasa sus argumentos a `_scrape_detalles` por nombre.

Antes iban por posición y reordenar la firma no daba error: el callback de
avance acababa en otro parámetro y el contador se quedaba quieto sin que nada
lo delatara. Estos tests fijan que el nombre es el contrato.
"""

from __future__ import annotations

import asyncio

from app.services import scraping_sunat

EMPRESA = {"ruc": "20608997106", "usuario": "USUARIO", "password": "cifrada"}


def _capturar(monkeypatch) -> dict:
    recibido: dict = {}

    def falso_scrape(ruc, usuario, password, comprobantes, **opciones):
        recibido.update(
            ruc=ruc,
            usuario=usuario,
            password=password,
            comprobantes=comprobantes,
            **opciones,
        )
        return {}

    monkeypatch.setattr(scraping_sunat, "_scrape_detalles", falso_scrape)
    monkeypatch.setattr(scraping_sunat, "decrypt_password", lambda _: "clave-en-claro")
    return recibido


def test_obtener_detalles_entrega_el_callback_de_avance(monkeypatch):
    recibido = _capturar(monkeypatch)

    def avisar(hechos: int, serie_numero: str) -> None:
        return None

    comprobantes = [{"serie_numero": "F001-1"}]
    asyncio.run(scraping_sunat.obtener_detalles(EMPRESA, comprobantes, progreso=avisar))

    assert recibido["progreso"] is avisar
    assert recibido["ruc"] == "20608997106"
    assert recibido["usuario"] == "USUARIO"
    assert recibido["password"] == "clave-en-claro"
    assert recibido["comprobantes"] is comprobantes


def test_toma_headless_y_timeout_de_la_configuracion(monkeypatch):
    monkeypatch.setattr(scraping_sunat.settings, "SUNAT_SCRAPER_HEADLESS", True)
    monkeypatch.setattr(scraping_sunat.settings, "SUNAT_SCRAPER_TIMEOUT_MS", 4321)
    recibido = _capturar(monkeypatch)

    asyncio.run(scraping_sunat.obtener_detalles(EMPRESA, []))

    assert recibido["headed"] is False
    assert recibido["timeout_ms"] == 4321


def test_la_llamada_gana_a_la_configuracion(monkeypatch):
    monkeypatch.setattr(scraping_sunat.settings, "SUNAT_SCRAPER_HEADLESS", True)
    recibido = _capturar(monkeypatch)

    asyncio.run(scraping_sunat.obtener_detalles(EMPRESA, [], headed=True, timeout_ms=999))

    assert recibido["headed"] is True
    assert recibido["timeout_ms"] == 999


def test_obtener_detalles_exige_clave_sol(monkeypatch):
    monkeypatch.setattr(scraping_sunat, "_scrape_detalles", lambda *a, **k: {})

    try:
        asyncio.run(scraping_sunat.obtener_detalles({"ruc": "1", "usuario": "u"}, []))
    except ValueError as fallo:
        assert "contraseña SOL" in str(fallo)
    else:
        raise AssertionError("se esperaba un ValueError sin contraseña guardada")
