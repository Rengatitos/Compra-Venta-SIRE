"""Parseo de CORS_ORIGINS.

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
