"""`obtener_detalles` pasa sus argumentos a `_scrape_detalles` por posición a
través de `asyncio.to_thread`. Reordenar la firma no da error: el callback de
avance acabaría en otro parámetro y el contador volvería a quedarse quieto."""

from __future__ import annotations

import asyncio

from app.services import scraping_sunat

EMPRESA = {"ruc": "20608997106", "usuario": "USUARIO", "password": "cifrada"}


def test_obtener_detalles_entrega_el_callback_de_avance(monkeypatch):
    recibido = {}

    def falso_scrape(ruc, usuario, password, comprobantes, debug, headed, slow_mo_ms, progreso):
        recibido.update(
            ruc=ruc,
            usuario=usuario,
            password=password,
            comprobantes=comprobantes,
            progreso=progreso,
        )
        return {}

    monkeypatch.setattr(scraping_sunat, "_scrape_detalles", falso_scrape)
    monkeypatch.setattr(scraping_sunat, "decrypt_password", lambda _: "clave-en-claro")

    def avisar(hechos: int, serie_numero: str) -> None:
        return None

    comprobantes = [{"serie_numero": "F001-1"}]
    asyncio.run(scraping_sunat.obtener_detalles(EMPRESA, comprobantes, progreso=avisar))

    assert recibido["progreso"] is avisar
    assert recibido["ruc"] == "20608997106"
    assert recibido["usuario"] == "USUARIO"
    assert recibido["password"] == "clave-en-claro"
    assert recibido["comprobantes"] is comprobantes


def test_obtener_detalles_exige_clave_sol(monkeypatch):
    monkeypatch.setattr(scraping_sunat, "_scrape_detalles", lambda *a: {})

    try:
        asyncio.run(scraping_sunat.obtener_detalles({"ruc": "1", "usuario": "u"}, []))
    except ValueError as fallo:
        assert "contraseña SOL" in str(fallo)
    else:
        raise AssertionError("se esperaba un ValueError sin contraseña guardada")
