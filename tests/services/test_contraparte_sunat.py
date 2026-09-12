import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.domain.comprobante import Libro
from app.repositories import comprobantes
from app.services.comprobante_service import serializar
from app.services.sunat.contraparte import receptor_html, receptor_listado


def test_receptor_de_listado_conserva_ceros_documento():
    assert receptor_listado(
        {
            "nroRucReceptor": "00123456  ",
            "codTipoDocReceptor": "01",
            "nroRucReceptorDesc": "00123456 - CLIENTE DE PRUEBA",
        }
    ) == {
        "razon_social": "CLIENTE DE PRUEBA",
        "documento_contraparte": "00123456",
        "tipo_doc_identidad": "1",
    }


def test_html_solo_lee_rotulos_explicitos():
    assert receptor_html(
        [
            ["RUC: 20123456789"],  # Cabecera del emisor, no el receptor.
            ["Señor(es)", ":", "CLIENTE DE PRUEBA"],
            ["DNI", ":", "00123456"],
            ["Descripción", ":", "ALOJAMIENTO"],
        ]
    ) == {
        "razon_social": "CLIENTE DE PRUEBA",
        "documento_contraparte": "00123456",
        "tipo_doc_identidad": "1",
    }


def test_sin_receptor_no_inventa_datos():
    assert receptor_listado({}) == {}
    assert receptor_html([["Glosa", ":", "ALOJAMIENTO"]]) == {}


def test_completa_ventas_sin_alterar_importes_ni_datos_sire():
    datos = {
        "libro": "ventas",
        "razon_social": "",
        "documento_contraparte": "",
        "igv": 5.7,
        "total": 60,
        "contraparte_sunat": {
            "razon_social": "CLIENTE",
            "documento_contraparte": "00123456",
            "tipo_doc_identidad": "1",
        },
    }
    salida = serializar(datos)
    assert salida["razon_social"] == "CLIENTE"
    assert salida["documento_contraparte"] == "00123456"
    assert salida["igv"] == 5.7 and salida["total"] == 60
    assert datos["razon_social"] == ""  # Se conserva la fuente original.
    datos["razon_social"] = "NOMBRE SIRE"
    assert serializar(datos)["razon_social"] == "NOMBRE SIRE"
    datos["libro"] = "compras"
    assert serializar(datos)["documento_contraparte"] == ""


def test_no_mezcla_tipo_de_otro_documento():
    assert (
        serializar(
            {
                "libro": "ventas",
                "documento_contraparte": "20123456789",
                "contraparte_sunat": {
                    "documento_contraparte": "00123456",
                    "tipo_doc_identidad": "1",
                },
            }
        )["tipo_doc_identidad"]
        == ""
    )


def test_guarda_complemento_con_identidad_y_procedencia(monkeypatch):
    coleccion = MagicMock()
    coleccion.update_one = AsyncMock()
    monkeypatch.setattr(comprobantes, "_col", lambda db: coleccion)
    asyncio.run(
        comprobantes.guardar_contraparte_sunat(
            None,
            "empresa",
            "202608",
            {"_id": "id", "_contraparte_sunat": {"razon_social": "CLIENTE"}},
        )
    )
    filtro, update = coleccion.update_one.call_args.args
    assert filtro == {"_id": "id", "empresa_id": "empresa", "periodo": "202608", "libro": "ventas"}
    assert update["$set"]["contraparte_sunat_fuente"] == "SUNAT SOL"
    assert "razon_social" not in update["$set"]
    assert "contraparte_sunat_consultada" in str(
        comprobantes._filtro_pendiente_sunat("empresa", "202608", Libro.VENTAS)
    )
