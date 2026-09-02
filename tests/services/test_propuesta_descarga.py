"""Paginación de la descarga de la propuesta.

Antes `descargar` pedía `page=1&perPage=100` fijo: cualquier periodo con más de
cien comprobantes se truncaba y nada lo delataba. En ventas eso es la norma
—los casos reales rondan los 400-900 comprobantes por periodo—, así que el
recorrido de páginas tiene que estar cubierto.
"""

from __future__ import annotations

import asyncio

import pytest

from app.domain.comprobante import Libro
from app.services.sunat import propuesta
from app.services.sunat.auth import ErrorSunat

EMPRESA = {"_id": "abc123", "ruc": "20608997106"}


class RespuestaFalsa:
    def __init__(self, status_code: int, datos=None, text: str = ""):
        self.status_code = status_code
        self._datos = datos
        self.text = text

    def json(self):
        return self._datos


def _registro(indice: int) -> dict:
    return {"numSerieCDP": "F001", "numCDP": str(indice), "fecEmision": "2026-06-15"}


def _montar(monkeypatch, respuestas, por_pagina=3, max_paginas=50):
    """Devuelve la lista de query params con la que se llamó a SUNAT."""
    llamadas: list[dict] = []
    pendientes = list(respuestas)

    async def peticion_autenticada(db, empresa, hacer_peticion):
        # `hacer_peticion` construye la request de verdad; ejecutarlo es lo que
        # deja ver qué `page` se pidió en cada vuelta.
        def requests_get(url, headers=None, params=None, timeout=None):
            llamadas.append(dict(params))
            return pendientes.pop(0)

        monkeypatch.setattr(propuesta.requests, "get", requests_get)
        return hacer_peticion("token")

    monkeypatch.setattr(propuesta, "peticion_autenticada", peticion_autenticada)
    monkeypatch.setattr(propuesta.settings, "SIRE_PER_PAGE", por_pagina)
    monkeypatch.setattr(propuesta.settings, "SIRE_MAX_PAGINAS", max_paginas)
    monkeypatch.setattr(
        propuesta.settings, "URL_SIRE_PROPUESTA_VENTAS", "https://sire/{PERIODO}/preliminar"
    )
    monkeypatch.setattr(
        propuesta.settings, "URL_SIRE_PROPUESTA", "https://sire/{PERIODO}/busqueda"
    )
    return llamadas


def _descargar(libro=Libro.VENTAS):
    return asyncio.run(propuesta.descargar(None, EMPRESA, "202606", libro))


def test_recorre_las_paginas_hasta_una_incompleta(monkeypatch):
    llamadas = _montar(
        monkeypatch,
        [
            RespuestaFalsa(200, {"registros": [_registro(1), _registro(2), _registro(3)]}),
            RespuestaFalsa(200, {"registros": [_registro(4), _registro(5), _registro(6)]}),
            RespuestaFalsa(200, {"registros": [_registro(7)]}),
        ],
    )

    registros = _descargar()

    assert len(registros) == 7
    assert [llamada["page"] for llamada in llamadas] == [1, 2, 3]


def test_una_pagina_exacta_pide_la_siguiente(monkeypatch):
    # Si la última página viene llena no hay forma de saber que se acabó: hay
    # que pedir una más y aceptar que venga vacía.
    _montar(
        monkeypatch,
        [
            RespuestaFalsa(200, {"registros": [_registro(1), _registro(2), _registro(3)]}),
            RespuestaFalsa(200, {"registros": []}),
        ],
    )

    assert len(_descargar()) == 3


def test_acepta_la_respuesta_como_lista_suelta(monkeypatch):
    _montar(monkeypatch, [RespuestaFalsa(200, [_registro(1)])])

    assert len(_descargar()) == 1


def test_el_tope_de_paginas_corta_y_avisa(monkeypatch, caplog):
    # Un endpoint que ignore `page` devolvería siempre lo mismo: sin freno, el
    # bucle no termina nunca.
    llena = [_registro(1), _registro(2), _registro(3)]
    _montar(
        monkeypatch,
        [RespuestaFalsa(200, {"registros": llena}) for _ in range(4)],
        max_paginas=3,
    )

    with caplog.at_level("WARNING"):
        registros = _descargar()

    assert len(registros) == 9
    assert "SIRE_MAX_PAGINAS" in caplog.text


def test_422_en_la_primera_pagina_significa_sin_propuesta(monkeypatch):
    _montar(monkeypatch, [RespuestaFalsa(422, text="sin propuesta")])

    assert _descargar() is None


def test_422_despues_de_la_primera_pagina_cierra_el_recorrido(monkeypatch):
    _montar(
        monkeypatch,
        [
            RespuestaFalsa(200, {"registros": [_registro(1), _registro(2), _registro(3)]}),
            RespuestaFalsa(422, text="sin más"),
        ],
    )

    assert len(_descargar()) == 3


def test_un_error_del_sire_se_propaga(monkeypatch):
    _montar(monkeypatch, [RespuestaFalsa(500, text="boom")])

    with pytest.raises(ErrorSunat):
        _descargar()


def test_compras_manda_cod_tipo_ope_y_ventas_no(monkeypatch):
    llamadas = _montar(monkeypatch, [RespuestaFalsa(200, {"registros": []})])
    _descargar(Libro.COMPRAS)
    assert llamadas[0]["codTipoOpe"] == "1"

    llamadas = _montar(monkeypatch, [RespuestaFalsa(200, {"registros": []})])
    _descargar(Libro.VENTAS)
    assert "codTipoOpe" not in llamadas[0]


def test_cada_libro_usa_su_propia_url(monkeypatch):
    monkeypatch.setattr(propuesta.settings, "URL_SIRE_PROPUESTA_VENTAS", "")
    monkeypatch.setattr(propuesta.settings, "URL_SIRE_PROPUESTA", "https://sire/{PERIODO}")

    with pytest.raises(ErrorSunat, match="URL_SIRE_PROPUESTA_VENTAS"):
        _descargar(Libro.VENTAS)


def test_perpage_se_recorta_al_maximo_del_sire(monkeypatch, caplog):
    # El SIRE responde 422 a cualquier perPage por encima de 100. Recortarlo
    # evita que un valor mal puesto en el entorno tumbe la descarga entera con
    # un error de validación que no dice de dónde sale el número.
    llamadas = _montar(
        monkeypatch, [RespuestaFalsa(200, {"registros": []})], por_pagina=500
    )

    with caplog.at_level("WARNING"):
        _descargar()

    assert llamadas[0]["perPage"] == propuesta.MAX_PER_PAGE
    assert "SIRE_PER_PAGE" in caplog.text


def test_el_total_de_la_paginacion_cierra_el_recorrido(monkeypatch):
    # Con `totalRegistros` no hace falta pedir una página de más para saber que
    # se acabó: dos páginas llenas que ya suman el total bastan.
    llena = [_registro(1), _registro(2), _registro(3)]
    llamadas = _montar(
        monkeypatch,
        [
            RespuestaFalsa(200, {"paginacion": {"totalRegistros": 6}, "registros": llena}),
            RespuestaFalsa(200, {"paginacion": {"totalRegistros": 6}, "registros": llena}),
        ],
    )

    assert len(_descargar()) == 6
    assert [llamada["page"] for llamada in llamadas] == [1, 2]


def test_sin_paginacion_se_sigue_pidiendo_hasta_una_pagina_corta(monkeypatch):
    # Los `totales` y la `paginacion` son un extra: si un endpoint no los
    # mandara, el recorrido tiene que seguir funcionando por tamaño de lote.
    llamadas = _montar(
        monkeypatch,
        [
            RespuestaFalsa(200, {"registros": [_registro(1), _registro(2), _registro(3)]}),
            RespuestaFalsa(200, {"registros": [_registro(4)]}),
        ],
    )

    assert len(_descargar()) == 4
    assert [llamada["page"] for llamada in llamadas] == [1, 2]
