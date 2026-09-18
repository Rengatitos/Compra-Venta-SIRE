"""Quién puede entrar al panel.

La regla es una lista de correos en el entorno, así que lo único que hay que
sostener es que la comparación no dependa de cómo se tecleó y que una lista
vacía no deje entrar a nadie.
"""

import pytest

from app.domain.usuario import esta_permitido, normalizar_correo

PERMITIDOS = ["espinozavaleracinver@gmail.com", "otro@example.com"]


@pytest.mark.parametrize(
    "correo",
    [
        "espinozavaleracinver@gmail.com",
        "  espinozavaleracinver@gmail.com  ",
        "EspinozaValeraCinver@Gmail.com",
    ],
    ids=["exacto", "con-espacios", "con-mayusculas"],
)
def test_acepta_el_correo_autorizado(correo: str):
    assert esta_permitido(correo, PERMITIDOS)


def test_la_allowlist_tambien_se_normaliza():
    # El .env lo escribe una persona: la lista puede venir con mayúsculas.
    assert esta_permitido("uno@example.com", [" Uno@EXAMPLE.com "])


def test_rechaza_un_correo_que_no_esta():
    assert not esta_permitido("ajeno@gmail.com", PERMITIDOS)


def test_una_allowlist_vacia_no_deja_entrar_a_nadie():
    assert not esta_permitido("espinozavaleracinver@gmail.com", [])


@pytest.mark.parametrize("correo", [None, "", "   "], ids=["none", "vacio", "espacios"])
def test_sin_correo_no_entra(correo):
    assert not esta_permitido(correo, PERMITIDOS)


def test_normalizar_tolera_none():
    assert normalizar_correo(None) == ""
