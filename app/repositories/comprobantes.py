from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.domain.comprobante import (
    Comprobante,
    EstadoProcesamiento,
    Libro,
    Origen,
)
from app.repositories._mongo import (
    NOMBRE_COL_COMPROBANTES,
    fecha_a_bson,
    fecha_desde_bson,
    monto_a_bson,
    monto_desde_bson,
)

_CAMPOS_MONTO = (
    "base_imponible",
    "igv",
    "base_imponible_dg",
    "igv_dg",
    "base_imponible_dgng",
    "igv_dgng",
    "base_imponible_dng",
    "igv_dng",
    "exonerado",
    "inafecto",
    "no_gravado",
    "isc",
    "icbper",
    "otros_tributos",
    "total",
)


def _col(db: AsyncIOMotorDatabase):
    return db[NOMBRE_COL_COMPROBANTES]


async def crear_indices(db: AsyncIOMotorDatabase) -> None:
    col = _col(db)
    await col.create_index([("empresa_id", 1), ("periodo", 1)])
    await col.create_index(
        [
            ("empresa_id", 1),
            ("periodo", 1),
            ("libro", 1),
            ("origen", 1),
            ("tipo_cp", 1),
            ("serie", 1),
            ("numero", 1),
        ],
        unique=True,
        name="uniq_comprobante",
    )


def a_documento(comprobante: Comprobante, empresa_id: str, periodo: str) -> dict[str, Any]:
    documento: dict[str, Any] = {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": comprobante.libro.value,
        "origen": comprobante.origen.value,
        "tipo_cp": comprobante.tipo_cp,
        "serie": comprobante.serie,
        "numero": comprobante.numero,
        "serie_numero": comprobante.serie_numero,
        "tipo_doc_identidad": comprobante.tipo_doc_identidad,
        "documento_contraparte": comprobante.documento_contraparte,
        "razon_social": comprobante.razon_social,
        "fecha_emision": fecha_a_bson(comprobante.fecha_emision),
        "fecha_vencimiento": fecha_a_bson(comprobante.fecha_vencimiento),
        "moneda": comprobante.moneda,
        "tipo_cambio": monto_a_bson(comprobante.tipo_cambio),
        "porcentaje_igv": monto_a_bson(comprobante.porcentaje_igv),
        "extra": comprobante.extra,
    }
    for campo in _CAMPOS_MONTO:
        documento[campo] = monto_a_bson(getattr(comprobante, campo))
    return documento


def desde_documento(documento: dict[str, Any]) -> Comprobante:
    montos = {campo: monto_desde_bson(documento.get(campo)) for campo in _CAMPOS_MONTO}
    tipo_cambio = documento.get("tipo_cambio")
    porcentaje_igv = documento.get("porcentaje_igv")
    return Comprobante(
        libro=Libro(documento.get("libro", Libro.COMPRAS.value)),
        origen=Origen(documento.get("origen", Origen.SIRE.value)),
        tipo_cp=documento.get("tipo_cp", ""),
        serie=documento.get("serie", ""),
        numero=documento.get("numero", ""),
        tipo_doc_identidad=documento.get("tipo_doc_identidad", ""),
        documento_contraparte=documento.get("documento_contraparte", ""),
        razon_social=documento.get("razon_social", ""),
        fecha_emision=fecha_desde_bson(documento.get("fecha_emision")),
        fecha_vencimiento=fecha_desde_bson(documento.get("fecha_vencimiento")),
        moneda=documento.get("moneda", "PEN"),
        tipo_cambio=monto_desde_bson(tipo_cambio) if tipo_cambio is not None else None,
        porcentaje_igv=(
            monto_desde_bson(porcentaje_igv) if porcentaje_igv is not None else None
        ),
        extra=documento.get("extra", {}),
        **montos,
    )


def filtro_identidad(
    empresa_id: str, periodo: str, comprobante: Comprobante
) -> dict[str, Any]:
    return {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": comprobante.libro.value,
        "origen": comprobante.origen.value,
        "tipo_cp": comprobante.tipo_cp,
        "serie": comprobante.serie,
        "numero": comprobante.numero,
    }


async def upsert(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, comprobante: Comprobante
) -> bool:
    documento = a_documento(comprobante, empresa_id, periodo)
    resultado = await _col(db).update_one(
        filtro_identidad(empresa_id, periodo, comprobante),
        {
            "$setOnInsert": {"estado_procesamiento": EstadoProcesamiento.SIRE_RECIBIDO.value},
            "$set": documento,
        },
        upsert=True,
    )
    return resultado.upserted_id is not None


async def listar(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    # El libro se filtra en la consulta, no después de paginar: con los dos
    # libros en el mismo periodo, una página de cien podía salir entera de
    # compras y dejar el listado de ventas vacío.
    filtro: dict[str, Any] = {"empresa_id": empresa_id, "periodo": periodo}
    if libro is not None:
        filtro["libro"] = libro.value
    cursor = _col(db).find(filtro).skip(skip).limit(limit)
    return await cursor.to_list(length=limit)


async def obtener(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    serie_numero: str,
    libro: Libro | None = None,
) -> dict[str, Any] | None:
    filtro: dict[str, Any] = {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "serie_numero": serie_numero,
    }
    # `serie_numero` no es único dentro de un periodo: la misma serie-número
    # puede existir como venta propia y como compra a un tercero.
    if libro is not None:
        filtro["libro"] = libro.value
    return await _col(db).find_one(filtro)


async def listar_pendientes_analisis(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    pendientes = [EstadoProcesamiento.SIRE_RECIBIDO.value, EstadoProcesamiento.ERROR_ANALISIS.value]
    filtro: dict[str, Any] = {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "$or": [
            {"estado_procesamiento": {"$in": pendientes}},
            {"estado_procesamiento": {"$exists": False}},
        ],
    }
    # El prompt de la IA depende del libro (una venta no es un gasto), así que
    # cada lote se analiza por separado.
    if libro is not None:
        filtro["libro"] = libro.value
    cursor = _col(db).find(filtro).sort([("_id", -1)])
    return await cursor.to_list(length=limit)


def _filtro_sin_detalle(empresa_id: str, periodo: str, libro: Libro) -> dict[str, Any]:
    # El libro no es opcional aquí: el scraper consulta "FE Recibidas" o "FE
    # Emitidas" según el libro, así que mezclar los dos en una extracción
    # buscaría cada comprobante en la bandeja equivocada.
    return {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": libro.value,
        "detalle_sunat": {"$exists": False},
    }


async def listar_sin_detalle(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cursor = _col(db).find(_filtro_sin_detalle(empresa_id, periodo, libro))
    return await cursor.to_list(length=limit or settings.SUNAT_MAX_COMPROBANTES)


async def contar_sin_detalle(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, libro: Libro
) -> int:
    """Cuántos quedan pendientes en total, con o sin tope.

    `listar_sin_detalle` corta en `SUNAT_MAX_COMPROBANTES`, y hasta ahora ese
    recorte era invisible: un periodo con más comprobantes que el tope
    terminaba el job como si los hubiera hecho todos.
    """
    return await _col(db).count_documents(_filtro_sin_detalle(empresa_id, periodo, libro))


async def guardar_analisis(
    db: AsyncIOMotorDatabase,
    documento_id: Any,
    metadata: dict[str, Any],
    estado: EstadoProcesamiento,
) -> None:
    await _col(db).update_one(
        {"_id": documento_id},
        {"$set": {"metadata_procesada": metadata, "estado_procesamiento": estado.value}},
    )


async def actualizar_estado(
    db: AsyncIOMotorDatabase, documento_id: Any, estado: EstadoProcesamiento
) -> None:
    await _col(db).update_one(
        {"_id": documento_id}, {"$set": {"estado_procesamiento": estado.value}}
    )


async def guardar_metadata(
    db: AsyncIOMotorDatabase, documento_id: Any, metadata: dict[str, Any]
) -> None:
    await _col(db).update_one({"_id": documento_id}, {"$set": {"metadata_procesada": metadata}})


async def guardar_detalle_sunat(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro,
    serie_numero: str,
    detalle: list[Any],
) -> None:
    # Sin `libro` en el filtro, un F001-1 que exista a la vez como venta y como
    # compra recibía el detalle en el documento equivocado.
    await _col(db).update_one(
        {
            "empresa_id": empresa_id,
            "periodo": periodo,
            "libro": libro.value,
            "serie_numero": serie_numero,
        },
        {"$set": {"detalle_sunat": detalle}},
    )


def _filtro_sin_pdf(empresa_id: str, periodo: str, libro: Libro) -> dict[str, Any]:
    # Mismo razonamiento que `_filtro_sin_detalle`: la bandeja del portal
    # depende del libro, así que la descarga tampoco puede mezclarlos.
    return {
        "empresa_id": empresa_id,
        "periodo": periodo,
        "libro": libro.value,
        "pdf_sunat": {"$exists": False},
    }


async def listar_sin_pdf(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cursor = _col(db).find(_filtro_sin_pdf(empresa_id, periodo, libro))
    return await cursor.to_list(length=limit or settings.SUNAT_MAX_PDFS)


async def contar_sin_pdf(
    db: AsyncIOMotorDatabase, empresa_id: str, periodo: str, libro: Libro
) -> int:
    """Cuántos siguen sin respaldo, ignorando el tope de `listar_sin_pdf`."""
    return await _col(db).count_documents(_filtro_sin_pdf(empresa_id, periodo, libro))


async def guardar_pdf_sunat(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro,
    serie_numero: str,
    ruta: str,
    bytes_: int,
) -> None:
    """Apunta dónde quedó el PDF de un comprobante.

    Se guarda la ruta **relativa** al almacén, no la absoluta: así mover el
    volumen a otro punto de montaje no invalida los punteros de la base.
    """
    await _col(db).update_one(
        {
            "empresa_id": empresa_id,
            "periodo": periodo,
            "libro": libro.value,
            "serie_numero": serie_numero,
        },
        {
            "$set": {
                "pdf_sunat": {
                    "ruta": ruta,
                    "bytes": bytes_,
                    "descargado_en": datetime.now(UTC),
                }
            }
        },
    )


async def guardar_xml_sunat(
    db: AsyncIOMotorDatabase,
    empresa_id: str,
    periodo: str,
    libro: Libro,
    serie_numero: str,
    ruta: str,
    bytes_: int,
) -> None:
    """Apunta dónde quedó el XML de un comprobante.

    Se guarda la ruta relativa al almacén. `xml_sunat` es sólo un puntero
    de respaldo, nunca un criterio de pendiente.
    """
    await _col(db).update_one(
        {
            "empresa_id": empresa_id,
            "periodo": periodo,
            "libro": libro.value,
            "serie_numero": serie_numero,
        },
        {
            "$set": {
                "xml_sunat": {
                    "ruta": ruta,
                    "bytes": bytes_,
                    "descargado_en": datetime.now(UTC),
                }
            }
        },
    )


async def periodos_disponibles(db: AsyncIOMotorDatabase, empresa_ids: list[str]) -> list[str]:
    periodos = await _col(db).distinct("periodo", {"empresa_id": {"$in": empresa_ids}})
    return sorted(periodos, reverse=True)


async def eliminar_de_periodo(db: AsyncIOMotorDatabase, empresa_id: str, periodo: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id, "periodo": periodo})
    return resultado.deleted_count


async def eliminar_de_empresa(db: AsyncIOMotorDatabase, empresa_id: str) -> int:
    resultado = await _col(db).delete_many({"empresa_id": empresa_id})
    return resultado.deleted_count
