import pytest

from app.services.glosa import obtener_glosa
from app.services.sunat.texto import corregir_codificacion


@pytest.mark.parametrize("original", ["BAÑO", "habitación", "JABÓN", "Ñ á é í ó ú ü"])
@pytest.mark.parametrize("encoding", ["latin-1", "cp1252"])
def test_repara_texto_sunat(original, encoding):
    incorrecto = original.encode("utf-8").decode(encoding)
    assert corregir_codificacion(incorrecto) == original


def test_respeta_texto_correcto_y_repara_fragmentos_mezclados():
    assert corregir_codificacion("BAÑO / BAÃ\x91O / habitación") == "BAÑO / BAÑO / habitación"
    assert corregir_codificacion("CAÑA, pingüino, 100 € / Ã") == "CAÑA, pingüino, 100 € / Ã"


def test_glosa_historica_se_corrige_antes_de_deduplicar():
    assert obtener_glosa({"detalle_sunat": [
        {"descripcion": "JAB BAÃ\x91O DOVE BLANCO X90GR"},
        {"descripcion": "JAB BAÑO DOVE BLANCO X90GR"},
    ]}) == "JAB BAÑO DOVE BLANCO X90GR"
