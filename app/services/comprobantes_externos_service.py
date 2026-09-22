"""Recepción y lectura de los comprobantes que manda sire-bot."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.domain.catalogos import describe_comprobante
from app.domain.comprobante_externo import ESTADO_RECIBIDO, periodo_de
from app.repositories import comprobantes_externos as repo_externos
from app.repositories._mongo import fecha_a_bson, fecha_desde_bson, monto_a_bson, monto_desde_bson
from app.schemas.comprobante_externo import ComprobanteExternoCreate
from app.services import imagenes_externas


class Duplicado(Exception):
    """Otro `id_externo` ya registró este mismo comprobante (clave natural)."""

    def __init__(self, existente_id: str | None):
        super().__init__(existente_id)
        self.existente_id = existente_id


def _iso(fecha: datetime | None) -> str | None:
    if fecha is None:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return fecha.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _texto_monto(valor: Any) -> str | None:
    if valor is None:
        return None
    return f"{monto_desde_bson(valor):.2f}"


def a_recibido(documento: dict[str, Any], ruc: str) -> dict[str, Any]:
    return {
        "id": str(documento["_id"]),
        "ruc": ruc,
        "periodo": documento["periodo"],
        "estado": documento["estado"],
        "creado_en": _iso(documento["creado_en"]),
    }


def a_respuesta(documento: dict[str, Any], ruc: str) -> dict[str, Any]:
    fecha: date | None = fecha_desde_bson(documento.get("fecha_operacion"))
    imagen = documento.get("imagen") or {}
    return {
        **a_recibido(documento, ruc),
        "id_externo": documento["id_externo"],
        "libro": documento["libro"],
        "fuente": documento["fuente"],
        "tipo_evidencia": documento["tipo_evidencia"],
        "tipo_cp": documento["tipo_cp"],
        "tipo_cp_descripcion": describe_comprobante(documento["tipo_cp"]),
        "serie": documento.get("serie") or "",
        "numero": documento.get("numero") or "",
        "nro_operacion": documento.get("nro_operacion"),
        "fecha_operacion": fecha.isoformat() if fecha else None,
        "hora_operacion": documento.get("hora_operacion"),
        "moneda": documento["moneda"],
        "total": _texto_monto(documento.get("total")) or "0.00",
        "base_imponible": _texto_monto(documento.get("base_imponible")),
        "igv": _texto_monto(documento.get("igv")),
        "contraparte": documento.get("contraparte") or {},
        "descripcion": documento.get("descripcion") or "",
        "confianza": documento.get("confianza"),
        "campos_dudosos": documento.get("campos_dudosos") or [],
        "dispositivo_id": documento.get("dispositivo_id") or "",
        "enviado_en": _iso(documento.get("enviado_en")),
        "tiene_imagen": bool(imagen.get("archivo")),
    }


def _monto(valor: Decimal | None):
    return monto_a_bson(valor) if valor is not None else None


def _documento(
    oid: ObjectId, empresa_id: str, datos: ComprobanteExternoCreate, archivo: str | None
) -> dict[str, Any]:
    nro_operacion = (datos.nro_operacion or "").strip() or None
    return {
        "_id": oid,
        "empresa_id": empresa_id,
        "id_externo": datos.id_externo,
        "libro": datos.libro.value,
        "fuente": datos.fuente.value,
        "tipo_evidencia": datos.tipo_evidencia.value,
        "tipo_cp": datos.tipo_cp,
        "serie": datos.serie.strip().upper(),
        "numero": datos.numero.strip(),
        "nro_operacion": nro_operacion,
        "fecha_operacion": fecha_a_bson(datos.fecha_operacion),
        "hora_operacion": datos.hora_operacion,
        "moneda": datos.moneda,
        "total": _monto(datos.total),
        "base_imponible": _monto(datos.base_imponible),
        "igv": _monto(datos.igv),
        "contraparte": datos.contraparte.model_dump(),
        "descripcion": datos.descripcion,
        "confianza": datos.confianza,
        "campos_dudosos": datos.campos_dudosos,
        "imagen": {
            "sha256": datos.imagen.sha256,
            "mime": datos.imagen.mime,
            "bytes": datos.imagen.bytes,
            "archivo": archivo,
        },
        "dispositivo_id": datos.dispositivo_id,
        "enviado_en": datos.enviado_en,
        "periodo": periodo_de(datos.fecha_operacion),
        "estado": ESTADO_RECIBIDO,
        "creado_en": datetime.now(UTC),
        "comprobante_id": None,
    }


async def recibir(
    db, empresa: dict, datos: ComprobanteExternoCreate
) -> tuple[dict[str, Any], bool]:
    """Registra el comprobante. Devuelve `(cuerpo, creado)`; `creado=False` es un reintento.

    Lanza `ImagenInvalida` (422) o `Duplicado` (409).
    """
    empresa_id = str(empresa["_id"])
    ruc = empresa["ruc"]

    previo = await repo_externos.por_id_externo(db, empresa_id, datos.id_externo)
    if previo:
        return a_recibido(previo, ruc), False

    foto: tuple[bytes, str, str] | None = None
    if datos.imagen.contenido_base64:
        foto = imagenes_externas.decodificar(datos.imagen.contenido_base64, datos.imagen.sha256)

    oid = ObjectId()
    archivo = imagenes_externas.guardar(empresa_id, str(oid), foto[0], foto[2]) if foto else None
    documento = _documento(oid, empresa_id, datos, archivo)
    if foto:
        documento["imagen"]["mime"] = foto[1]

    try:
        await repo_externos.insertar(db, documento)
    except DuplicateKeyError:
        if archivo:
            imagenes_externas.eliminar(empresa_id, archivo)
        # Dos reintentos del mismo envío que llegan a la vez: el otro ganó.
        previo = await repo_externos.por_id_externo(db, empresa_id, datos.id_externo)
        if previo:
            return a_recibido(previo, ruc), False
        existente = await repo_externos.conflicto(db, empresa_id, documento)
        raise Duplicado(str(existente["_id"]) if existente else None) from None

    return a_recibido(documento, ruc), True


async def listar(
    db,
    empresa: dict,
    *,
    libro: str | None,
    periodo: str | None,
    fuente: str | None,
    skip: int,
    limit: int,
) -> dict[str, Any]:
    empresa_id = str(empresa["_id"])
    documentos, total = await repo_externos.listar(
        db, empresa_id, libro=libro, periodo=periodo, fuente=fuente, skip=skip, limit=limit
    )
    return {
        "items": [a_respuesta(d, empresa["ruc"]) for d in documentos],
        "total": total,
        "periodos": await repo_externos.periodos(db, empresa_id, libro),
    }


async def obtener(db, empresa: dict, id_: str) -> dict[str, Any] | None:
    documento = await repo_externos.obtener(db, str(empresa["_id"]), id_)
    return a_respuesta(documento, empresa["ruc"]) if documento else None


async def imagen(db, empresa: dict, id_: str) -> tuple[bytes, str] | None:
    empresa_id = str(empresa["_id"])
    documento = await repo_externos.obtener(db, empresa_id, id_)
    datos_imagen = (documento or {}).get("imagen") or {}
    archivo = datos_imagen.get("archivo")
    if not archivo:
        return None
    contenido = imagenes_externas.leer(empresa_id, archivo)
    if contenido is None:
        return None
    return contenido, datos_imagen.get("mime") or "image/jpeg"
