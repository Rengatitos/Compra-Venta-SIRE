"""Fotos de los comprobantes externos, en disco.

Ruta: `{COMPROBANTES_EXTERNOS_DIR}/{empresa_id}/{id}.{ext}`.

No se confía en el `mime` que declara el bot: el formato se decide por la firma
de los bytes, y el sha256 tiene que coincidir con el que viene en el cuerpo.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_BYTES = 10 * 1024 * 1024


class ImagenInvalida(ValueError):
    pass


def _formato(contenido: bytes) -> tuple[str, str] | None:
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def decodificar(contenido_base64: str, sha256_declarado: str) -> tuple[bytes, str, str]:
    """Devuelve `(bytes, mime, extension)` o lanza `ImagenInvalida`."""
    try:
        contenido = base64.b64decode(contenido_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ImagenInvalida("imagen.contenido_base64 no es base64 válido") from None

    if len(contenido) > MAX_BYTES:
        raise ImagenInvalida(f"La imagen supera el máximo de {MAX_BYTES} bytes")
    if hashlib.sha256(contenido).hexdigest() != sha256_declarado:
        raise ImagenInvalida("El sha256 de la imagen no coincide con imagen.sha256")

    formato = _formato(contenido)
    if formato is None:
        raise ImagenInvalida("La imagen debe ser JPEG, PNG o WEBP")
    return contenido, *formato


def _carpeta(empresa_id: str) -> Path:
    return Path(settings.COMPROBANTES_EXTERNOS_DIR) / empresa_id


def guardar(empresa_id: str, id_: str, contenido: bytes, extension: str) -> str:
    """Escribe la foto y devuelve el nombre de archivo que se guarda en el documento."""
    carpeta = _carpeta(empresa_id)
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = f"{id_}.{extension}"
    (carpeta / archivo).write_bytes(contenido)
    return archivo


def leer(empresa_id: str, archivo: str) -> bytes | None:
    ruta = _carpeta(empresa_id) / Path(archivo).name
    try:
        return ruta.read_bytes()
    except FileNotFoundError:
        return None


def eliminar(empresa_id: str, archivo: str) -> None:
    (_carpeta(empresa_id) / Path(archivo).name).unlink(missing_ok=True)


def eliminar_de_empresa(empresa_id: str) -> None:
    carpeta = _carpeta(empresa_id)
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)
        logger.info("Fotos de comprobantes externos eliminadas empresa_id=%s", empresa_id)
