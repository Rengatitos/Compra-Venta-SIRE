import pytest
from pydantic import ValidationError

from app.services.ollama_rag import (
    Naturaleza,
    a_formato_legacy,
    aplicar_reglas_deterministicas,
)


def _naturaleza(**cambios):
    base = {
        "registro": "COMPRA",
        "clasificacion": "COSTO",
        "subtipo_operacion": "COMPRA_GIRO",
        "condicion_pago": "DESCONOCIDO",
        "origen_bien": "COMPRA",
        "relacion_giro": "GIRO",
        "detalle_lineas": [],
        "estado_tributario": "APTO",
        "explicacion": "Mercadería para reventa",
    }
    return Naturaleza(**(base | cambios))


def test_pago_ausente_permanece_desconocido():
    assert _naturaleza().condicion_pago == "DESCONOCIDO"


def test_mixto_exige_detalle_de_lineas():
    with pytest.raises(ValidationError):
        _naturaleza(clasificacion="MIXTO")


def test_formato_legacy_conserva_resultado_y_cuentas():
    salida = a_formato_legacy(
        {
            **_naturaleza().model_dump(),
            "cuenta_base": "6011020",
            "cuenta_contrapartida": "4212",
            "confianza": 0.91,
            "requiere_revision": False,
            "evidencias": [{"id": "FS001"}],
        }
    )
    assert salida["resultado"] == "COSTO"
    assert salida["rag"]["cuenta_base"] == "6011020"


def test_formato_legacy_reproduce_contrato_gemini_con_igv_y_detalle():
    salida = a_formato_legacy(
        {
            **_naturaleza(
                clasificacion="MIXTO",
                detalle_lineas=[{"descripcion": "Combustible", "clasificacion": "GASTO"}],
            ).model_dump(),
            "cuenta_base": "6361",
            "cuenta_contrapartida": "4212",
            "confianza": 0.72,
            "requiere_revision": True,
            "evidencias": [{"id": "R1"}],
        },
        {
            "tipo_cp": "01",
            "tipo_doc_identidad": "6",
            "igv": 18,
            "detalle_sunat": [{"descripcion": "COMBUSTIBLE", "cantidad": 2, "importe": 100}],
        },
    )
    assert salida["resultado"] == "NO DETERMINADO"
    assert salida["condicion_igv"] == "Gravado"
    assert salida["detalle"][0]["producto"] == "COMBUSTIBLE"
    assert salida["rag"]["codigo_comprobante"] == "01"
    assert salida["rag"]["codigo_identidad"] == "6"
    assert salida["rag"]["glosa"] == "COMBUSTIBLE"


def test_analisis_posterior_conserva_la_glosa_extraida_de_sunat():
    salida = a_formato_legacy(
        {
            **_naturaleza().model_dump(),
            "cuenta_base": "603202521",
            "cuenta_contrapartida": "4212",
            "confianza": 0.99,
            "requiere_revision": False,
            "evidencias": [{"id": "H1"}],
        },
        {
            "metadata_procesada": {"rag": {"glosa": "GLOSA ORIGINAL SUNAT"}},
            "detalle_sunat": [{"descripcion": "Texto posterior"}],
        },
    )
    assert salida["rag"]["glosa"] == "GLOSA ORIGINAL SUNAT"


def test_reventa_gana_sobre_una_clasificacion_erronea_del_modelo():
    resultado = aplicar_reglas_deterministicas(
        _naturaleza(clasificacion="ACTIVO", condicion_pago="NO_APLICA"),
        {
            "registro": "COMPRA",
            "items": [{"descripcion": "Parabrisas para reventa"}],
            "condicion_pago_texto": "",
            "fecha_vencimiento": "",
            "cuotas": [],
        },
    )
    assert resultado.clasificacion == "COSTO"
    assert resultado.condicion_pago == "DESCONOCIDO"
    assert resultado.relacion_giro == "GIRO"
