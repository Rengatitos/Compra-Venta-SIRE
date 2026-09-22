import hashlib
import io
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.core.captura_config import CapturaSettings


class StorageProvider(Protocol):
    def put(self, content: bytes) -> str: ...
    def read(self, key: str) -> bytes: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError("Clave de almacenamiento inválida")
        return path

    def put(self, content: bytes) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = uuid4().hex
        path = self.path(key)
        with path.open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        return key

    def read(self, key: str) -> bytes:
        return self.path(key).read_bytes()


def storage(settings: CapturaSettings) -> StorageProvider:
    if settings.STORAGE_PROVIDER != "local":
        raise ValueError("Proveedor de almacenamiento no implementado")
    return LocalStorage(settings.UPLOAD_DIR)


def inspect_file(content: bytes, settings: CapturaSettings) -> dict:
    """Valida el contenido real antes de decodificarlo en el worker."""
    if not content or len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise ValueError("Archivo vacío o demasiado grande")
    if content.startswith(b"%PDF-"):
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(content)
        try:
            if not 0 < len(pdf) <= settings.MAX_PDF_PAGES:
                raise ValueError("El PDF excede el límite de páginas")
        finally:
            pdf.close()
        mime = "application/pdf"
    else:
        from PIL import Image

        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height > 24_000_000:
                raise ValueError("Imagen demasiado grande")
            formats = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
            if image.format not in formats:
                raise ValueError("Formato de imagen no admitido")
            mime = formats[image.format]
            image.verify()
    return {"mime": mime, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
