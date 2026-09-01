"""El modelo de respuesta no puede quedarse atrás del serializador.

`ComprobanteResponse` descarta en silencio cualquier clave que no declare, así
que un campo nuevo en el dominio llega al Excel —que va directo a
`serializar_lote`— pero desaparece de la API. Ya pasó con el desglose por
destino y la tasa de IGV: el Excel los escribía y `GET /comprobantes` no.
"""

from __future__ import annotations

from app.domain.comprobante import Libro
from app.repositories.comprobantes import a_documento
from app.schemas.comprobante import ComprobanteResponse
from app.services.comprobante_service import serializar, texto_para_ia
from app.services.sunat.propuesta import a_comprobante

PAYLOAD = {
    "numSerieCDP": "F001",
    "numCDP": "7",
    "codTipoCDP": "01",
    "numDocIdentidadProveedor": "20129646099",
    "fecEmision": "2026-06-15",
    "porTasaIGV": 0.18,
    "montos": {
        "mtoBIGravadaDG": 100.0,
        "mtoIgvIpmDG": 18.0,
        "mtoBIGravadaDGNG": 30.0,
        "mtoIgvIpmDGNG": 5.4,
        "mtoBIGravadaDNG": 20.0,
        "mtoIgvIpmDNG": 3.6,
        "mtoTotalCp": 177.0,
    },
}


def _documento(payload: dict | None = None) -> dict:
    documento = a_documento(
        a_comprobante(payload or PAYLOAD, Libro.COMPRAS), "empresa1", "202606"
    )
    documento["estado_procesamiento"] = "sire_recibido"
    return documento


def test_la_respuesta_no_pierde_ningun_campo_del_serializador():
    salida = serializar(_documento())
    respuesta = ComprobanteResponse(**salida).model_dump()

    descartados = sorted(set(salida) - set(respuesta))
    assert not descartados, f"campos que la API descarta: {descartados}"


def test_el_desglose_por_destino_viaja_en_la_respuesta():
    respuesta = ComprobanteResponse(**serializar(_documento())).model_dump()

    assert respuesta["base_imponible"] == 150.0
    assert respuesta["base_imponible_dg"] == 100.0
    assert respuesta["base_imponible_dgng"] == 30.0
    assert respuesta["base_imponible_dng"] == 20.0
    assert respuesta["igv_dg"] == 18.0


def test_la_tasa_viaja_en_puntos_porcentuales():
    respuesta = ComprobanteResponse(**serializar(_documento())).model_dump()
    assert respuesta["porcentaje_igv"] == 18.0


def test_sin_tasa_declarada_el_campo_es_nulo():
    # `0.0` se leería como "tasa cero", que no es lo mismo que "SUNAT no la
    # mandó" — y es lo que distingue una celda vacía de un 0 % en el Excel.
    payload = {k: v for k, v in PAYLOAD.items() if k != "porTasaIGV"}
    respuesta = ComprobanteResponse(**serializar(_documento(payload))).model_dump()
    assert respuesta["porcentaje_igv"] is None


class TestTextoParaIA:
    def test_incluye_la_tasa_y_el_desglose(self):
        texto = texto_para_ia(_documento())
        assert "Tasa de IGV declarada: 18.0%" in texto
        assert "gravadas y no gravadas: 30.0 / 5.4" in texto

    def test_sin_reparto_no_se_repite_la_base_tres_veces(self):
        solo_dg = {
            **PAYLOAD,
            "montos": {
                **PAYLOAD["montos"],
                "mtoBIGravadaDGNG": 0.0,
                "mtoIgvIpmDGNG": 0.0,
                "mtoBIGravadaDNG": 0.0,
                "mtoIgvIpmDNG": 0.0,
            },
        }
        assert "Destino de la adquisición" not in texto_para_ia(_documento(solo_dg))
