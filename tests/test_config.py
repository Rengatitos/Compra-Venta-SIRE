"""Parseo de las listas que se leen del entorno.

Regresión: `CORS_ORIGINS` es `list[str]`, y pydantic-settings decodifica los
campos complejos del entorno como JSON antes de aplicar los validadores. Sin
`NoDecode`, el formato separado por comas que documenta `.env.example` hacía
fallar el arranque con un JSONDecodeError, y con `NoDecode` a secas se rompía la
forma JSON que ya usaban los despliegues. Se aceptan las dos.
"""

import pytest
from pydantic import ValidationError

from app.core.config import CORS_ORIGINS_POR_DEFECTO, Settings

ESPERADO = ["https://a.pe", "https://b.pe"]


@pytest.mark.parametrize(
    "valor",
    [
        "https://a.pe,https://b.pe",
        "https://a.pe, https://b.pe ",
        '["https://a.pe","https://b.pe"]',
        '[ "https://a.pe" , "https://b.pe" ]',
    ],
    ids=["comas", "comas-con-espacios", "json", "json-con-espacios"],
)
def test_acepta_ambos_formatos(valor: str):
    assert Settings(CORS_ORIGINS=valor).CORS_ORIGINS == ESPERADO


def test_un_solo_origen():
    assert Settings(CORS_ORIGINS="https://solo.pe").CORS_ORIGINS == ["https://solo.pe"]


def test_valor_vacio_cae_al_default():
    # Un valor vacío significa "no lo configuré". Devolver una lista vacía
    # bloquearía al frontend sin ninguna pista del motivo.
    assert Settings(CORS_ORIGINS="").CORS_ORIGINS == CORS_ORIGINS_POR_DEFECTO


def test_una_lista_pasa_sin_tocar():
    assert Settings(CORS_ORIGINS=["https://a.pe"]).CORS_ORIGINS == ["https://a.pe"]


def test_json_malformado_falla_con_mensaje_util():
    with pytest.raises(ValidationError, match="no se pudo decodificar"):
        Settings(CORS_ORIGINS='["https://a.pe",')


# Parseo de GOOGLE_ALLOWED_EMAILS. Comparte forma con CORS_ORIGINS —y por tanto
# la necesidad de `NoDecode`— pero no comparte el trato del valor vacío, que es
# justo lo que fijan los tests de abajo.

CORREOS = ["uno@example.com", "dos@example.com"]


@pytest.mark.parametrize(
    "valor",
    [
        "uno@example.com,dos@example.com",
        " uno@example.com , dos@example.com ",
        "UNO@Example.com,Dos@EXAMPLE.com",
        '["uno@example.com","dos@example.com"]',
        '[ "UNO@example.com" , " dos@example.com " ]',
    ],
    ids=["comas", "espacios", "mayusculas", "json", "json-sucio"],
)
def test_correos_acepta_ambos_formatos_y_normaliza(valor: str):
    assert Settings(GOOGLE_ALLOWED_EMAILS=valor).GOOGLE_ALLOWED_EMAILS == CORREOS


def test_correos_una_lista_tambien_se_normaliza():
    # Es la forma en la que llega al construir Settings a mano en los tests.
    entrada = [" UNO@example.com ", "dos@EXAMPLE.com"]
    assert Settings(GOOGLE_ALLOWED_EMAILS=entrada).GOOGLE_ALLOWED_EMAILS == CORREOS


def test_correos_vacio_no_deja_entrar_a_nadie():
    # Al revés que CORS_ORIGINS, y a propósito: este campo falla cerrado. Un
    # default permisivo abriría el panel a cualquier cuenta de Google, así que
    # "no lo configuré" tiene que significar "no entra nadie".
    assert Settings(GOOGLE_ALLOWED_EMAILS="").GOOGLE_ALLOWED_EMAILS == []


def test_correos_json_malformado_falla_con_mensaje_util():
    with pytest.raises(ValidationError, match="no se pudo decodificar"):
        Settings(GOOGLE_ALLOWED_EMAILS='["uno@example.com",')
