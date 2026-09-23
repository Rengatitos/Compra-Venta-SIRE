"""Puente entre los comprobantes guardados y el clasificador contable.

El motor (RAG + Gemini) tiene sus propias pruebas; aquí se comprueba lo que
pone esta API: qué hechos le llegan de cada comprobante, cómo se guarda lo que
devuelve y cuándo su cuenta base llega al Excel.
"""

from __future__ import annotations

import asyncio

import jwt
import pytest

from app.domain.comprobante import Libro
from app.repositories.comprobantes import a_documento
from app.schemas.comprobante import ComprobanteResponse
from app.services import clasificacion_service, plantilla_excel
from app.services.clasificacion_service import SinDescripcion, construir_solicitud
from app.services.clasificador.schemas import ClassificationResponse
from app.services.comprobante_service import serializar
from app.services.sunat.propuesta import a_comprobante

PAYLOAD = {
    "numSerieCDP": "F001",
    "numCDP": "7",
    "codTipoCDP": "01",
    "numDocIdentidadProveedor": "20486339510",
    "nomRazonSocialProveedor": "SERVICIOS CONTABLES SA",
    "fecEmision": "2026-06-15",
    "montos": {"mtoBIGravadaDG": 1750.0, "mtoIgvIpmDG": 315.0, "mtoTotalCp": 2065.0},
}

EMPRESA = {
    "_id": "empresa1",
    "ruc": "20610202251",
    "nombre": "CORPORACION UNICACHI",
    "actividades_economicas": [
        {"tipo": "PRINCIPAL", "ciiu": "4663", "descripcion": "VENTA AL POR MAYOR"},
    ],
}


def _documento(**extra) -> dict:
    documento = a_documento(a_comprobante(PAYLOAD, Libro.COMPRAS), "empresa1", "202606")
    return {"_id": "doc1", "estado_procesamiento": "sire_recibido", **documento, **extra}


DETALLE = [
    {"cantidad": "1.00", "unidad_medida": "UNIDAD", "descripcion": "SERVICIO CONTABLE JUNIO",
     "valor_unitario": "1,750.00"},
    {"cantidad": "", "descripcion": "   "},
]


def _token(ciiu: str) -> str:
    return jwt.encode({"userdata": {"map": {"ddpData": {"ddp_ciiu": ciiu}}}}, "x")


class TestConstruirSolicitud:
    def test_lleva_los_items_del_detalle_y_los_hechos_del_comprobante(self):
        solicitud = construir_solicitud(_documento(detalle_sunat=DETALLE), EMPRESA)

        assert [i.descripcion for i in solicitud.items] == ["SERVICIO CONTABLE JUNIO"]
        assert solicitud.items[0].cantidad == 1.0
        assert solicitud.items[0].valor_unitario == 1750.0
        cp = solicitud.comprobante
        assert cp.libro == "COMPRAS"
        assert cp.tipo_cp.codigo == "01"
        assert cp.tipo_cp.descripcion
        assert (cp.serie, cp.numero, cp.fecha_emision) == ("F001", "7", "2026-06-15")
        assert cp.importes.base_imponible == 1750.0
        assert cp.importes.total == 2065.0
        assert cp.contraparte.numero_documento == "20486339510"
        assert solicitud.empresa.ruc == "20610202251"
        assert [a.ciiu_v4 for a in solicitud.empresa.actividades_economicas] == ["4663"]

    def test_sin_actividades_registradas_usa_el_ciiu_del_token_sunat(self):
        empresa = {"ruc": "20610202251", "sunat_token": _token("5510")}
        solicitud = construir_solicitud(_documento(detalle_sunat=DETALLE), empresa)
        assert [a.ciiu_v4 for a in solicitud.empresa.actividades_economicas] == ["5510"]

    def test_la_contraparte_registrada_aporta_sus_actividades(self):
        proveedor = {"ruc": "20486339510", "actividades_economicas": [{"ciiu": "6920"}]}
        solicitud = construir_solicitud(_documento(detalle_sunat=DETALLE), EMPRESA, proveedor)
        actividades = solicitud.comprobante.contraparte.actividades_economicas
        assert [a.ciiu_v4 for a in actividades] == ["6920"]

    def test_sin_items_describe_la_operacion_con_la_glosa(self):
        solicitud = construir_solicitud(_documento(glosa="Honorarios de auditoria"), EMPRESA)
        assert [i.descripcion for i in solicitud.items] == ["Honorarios de auditoria"]

    def test_sin_items_ni_glosa_no_hay_nada_que_clasificar(self):
        with pytest.raises(SinDescripcion):
            construir_solicitud(_documento(), EMPRESA)


def _respuesta(requiere_revision: bool = False) -> ClassificationResponse:
    return ClassificationResponse(
        clasificacion="COMPRA / SERVICIO",
        subtipo="SERVICIO CONTABLE",
        cuenta_base_imponible={"codigo": "6323094", "descripcion": "AUDITORIA Y CONTABLE - ADM"},
        cuenta_total={"codigo": "4212", "descripcion": "EMITIDAS"},
        condicion_igv="GRAVADO",
        confianza=0.81,
        razon="Servicio contable de soporte administrativo.",
        requiere_revision=requiere_revision,
        confianza_rag=0.8,
    )


def test_la_clasificacion_guardada_sale_en_la_respuesta_del_comprobante():
    guardada = clasificacion_service.a_documento(_respuesta(), "gemini-x")
    visible = serializar(_documento(clasificacion_contable=guardada))

    respuesta = ComprobanteResponse.model_validate(visible)

    assert respuesta.clasificacion_contable.cuenta_base.codigo == "6323094"
    assert respuesta.clasificacion_contable.requiere_revision is False
    assert respuesta.clasificacion_contable.modelo == "gemini-x"


class TestCuentaEnExcel:
    def test_sin_clasificar_la_cuenta_base_queda_vacia(self):
        assert plantilla_excel._cuenta_contable({}) is None

    def test_la_cuenta_base_pasa_si_no_requiere_revision(self):
        clasificacion = clasificacion_service.a_documento(_respuesta(False), "m")
        comprobante = {"clasificacion_contable": clasificacion}
        assert plantilla_excel._cuenta_contable(comprobante) == "6323094"

    def test_no_pasa_si_requiere_revision(self):
        clasificacion = clasificacion_service.a_documento(_respuesta(True), "m")
        assert plantilla_excel._cuenta_contable({"clasificacion_contable": clasificacion}) is None

    def test_un_codigo_demasiado_largo_no_se_recorta(self):
        comprobante = {"clasificacion_contable": {
            "requiere_revision": False, "cuenta_base": {"codigo": "63230940001"},
        }}
        assert plantilla_excel._cuenta_contable(comprobante) is None


