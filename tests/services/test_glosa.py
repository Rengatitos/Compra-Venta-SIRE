from app.services.comprobante_service import serializar
from app.services.glosa import obtener_glosa


def test_glosa_usa_todos_los_items_sunat_sin_duplicados():
    documento = {
        "detalle_sunat": [
            {"descripcion": " Aceite "},
            {"descripcion": "Filtro"},
            {"descripcion": "Aceite"},
            None,
            {},
        ],
        "metadata_procesada": {"rag": {"glosa": "Incorrecta"}, "cuenta_contable": "6011"},
    }
    salida = serializar(documento)
    assert salida["glosa"] == "Aceite / Filtro"
    assert salida["analisis"] is None


def test_glosa_manual_tiene_prioridad_incluso_si_se_vacia():
    documento = {"detalle_sunat": [{"descripcion": "Original"}], "glosa": " Corregida "}
    assert obtener_glosa(documento) == "Corregida"
    documento["glosa"] = ""
    assert obtener_glosa(documento) == ""


def test_sin_detalle_no_inventa_glosa():
    assert obtener_glosa({"razon_social": "Proveedor"}) == ""


def test_guardar_glosa_no_sobrescribe_el_detalle_ni_el_estado():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.repositories.comprobantes import guardar_glosa

    db = MagicMock()
    coleccion = db.__getitem__.return_value
    coleccion.update_one = AsyncMock()
    asyncio.run(guardar_glosa(db, "comprobante-id", "Glosa corregida"))
    coleccion.update_one.assert_awaited_once_with(
        {"_id": "comprobante-id"}, {"$set": {"glosa": "Glosa corregida"}}
    )


def test_rutas_ia_retiradas_y_extraccion_disponible():
    from fastapi import FastAPI

    from app.api.v1.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    rutas = app.openapi()["paths"]
    assert not any(
        fragmento in ruta
        for ruta in rutas
        for fragmento in ("/rag", "/analisis", "/referencias", "/ai-classification")
    )
    assert any("/detalle" in ruta for ruta in rutas)
    assert any("/pdfs" in ruta for ruta in rutas)
