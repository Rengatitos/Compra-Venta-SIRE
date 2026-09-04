"""Dónde viven los PDFs que se descargan del portal SOL.

La estructura la pidió el cliente para que el auditor pueda navegarla a mano,
así que es parte del contrato y no un detalle interno:

    {SUNAT_DATA_DIR}/{ruc}/{libro}/{año}/{mes}/{tipo}/{serie}-{numero}.pdf
    data/20608997106/ventas/2026/08/boletas/B001-00001234.pdf

El RUC no estaba en la estructura original —la pensaron para una sola empresa—,
pero la aplicación es multiempresa: sin él, dos empresas con el mismo periodo
escriben en la misma carpeta y la segunda sobreescribe a la primera.

Este módulo sólo resuelve rutas y bytes. No sabe de Mongo ni de Playwright.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.core.config import settings
from app.domain.comprobante import Libro, normalizar_tipo_cp
from app.domain.periodo import anio_mes

logger = logging.getLogger(__name__)

# Raíz del repo, igual que `LOG_DIR` en `scraping_sunat`: este archivo está en
# `app/services/`, así que dos niveles arriba es el proyecto.
_RAIZ_REPO = Path(__file__).resolve().parents[2]

# Una carpeta por tipo de documento, con los nombres que usa el cliente en sus
# anotaciones. Los códigos son los mismos que ya maneja el scraper para elegir
# la bandeja del portal.
CARPETAS_POR_TIPO = {
    "01": "facturas",
    "03": "boletas",
    "07": "notas_credito",
    "08": "notas_debito",
}
CARPETA_POR_DEFECTO = "otros"

# Lo que se acepta en un segmento de ruta. Las series y los números vienen de
# SUNAT y de archivos de terceros: han aparecido con espacios y con caracteres
# invisibles, y cualquiera de los dos rompe una ruta o, peor, la reescribe.
_PROHIBIDO = re.compile(r"[^A-Za-z0-9._-]+")


def raiz() -> Path:
    """Directorio base configurado, resuelto contra el root del repo."""
    configurado = Path(settings.SUNAT_DATA_DIR)
    return configurado if configurado.is_absolute() else _RAIZ_REPO / configurado


def _segmento(valor: object, *, campo: str) -> str:
    """Un tramo de ruta seguro, o `ValueError` si el valor no sirve.

    Se rechaza en vez de sustituir por un relleno: un PDF guardado en
    `.../_/_.pdf` es un archivo que nadie va a poder relacionar con su
    comprobante, y es peor que no tenerlo.

    Los espacios y los caracteres invisibles se limpian —aparecen en los
    archivos reales y no cambian de qué comprobante se habla—, pero un
    separador de rutas o un `..` se rechaza: en una serie o un RUC no significa
    "límpiame", significa que el dato no es lo que se esperaba.
    """
    crudo = str(valor or "").strip()
    if any(marca in crudo for marca in ("/", "\\", "..")):
        raise ValueError(f"{campo} no puede contener separadores de ruta: {valor!r}")

    limpio = _PROHIBIDO.sub("", crudo)
    if not limpio or set(limpio) <= {"."}:
        raise ValueError(f"{campo} no tiene ningún carácter utilizable en una ruta: {valor!r}")
    return limpio


def carpeta_de_tipo(tipo_cp: object) -> str:
    return CARPETAS_POR_TIPO.get(normalizar_tipo_cp(tipo_cp), CARPETA_POR_DEFECTO)


def raiz_periodo(ruc: str, libro: Libro, periodo: str) -> Path:
    """`{raíz}/{ruc}/{libro}/{año}/{mes}` — el nivel que se empaqueta en ZIP."""
    anio, mes = anio_mes(periodo)
    return raiz() / _segmento(ruc, campo="RUC") / libro.value / f"{anio:04d}" / f"{mes:02d}"


def ruta_pdf(
    ruc: str,
    libro: Libro,
    periodo: str,
    tipo_cp: object,
    serie: str,
    numero: str,
    *,
    extension: str = "pdf",
    subcarpeta: str | None = None,
) -> Path:
    """Ruta absoluta del archivo (PDF o XML) de un comprobante.

    Valida que el resultado caiga dentro de la raíz configurada: los tramos
    salen de datos de SUNAT y de archivos que sube el usuario, así que no son
    de fiar aunque el saneado ya quite lo evidente.
    """
    ext = _segmento(extension.lstrip("."), campo="La extensión")
    nombre = f"{_segmento(serie, campo='La serie')}-{_segmento(numero, campo='El número')}.{ext}"
    carpeta = (
        _segmento(subcarpeta, campo="La subcarpeta") if subcarpeta else carpeta_de_tipo(tipo_cp)
    )
    destino = (raiz_periodo(ruc, libro, periodo) / carpeta / nombre).resolve()

    base = raiz().resolve()
    if not destino.is_relative_to(base):
        raise ValueError(f"La ruta calculada se sale del almacén: {destino}")
    return destino


def guardar(
    ruc: str,
    libro: Libro,
    periodo: str,
    tipo_cp: object,
    serie: str,
    numero: str,
    contenido: bytes,
    *,
    extension: str = "pdf",
    subcarpeta: str | None = None,
) -> Path:
    """Escribe el archivo (PDF o XML) y devuelve su ruta absoluta."""
    if not contenido:
        raise ValueError("No hay contenido que guardar")

    destino = ruta_pdf(
        ruc,
        libro,
        periodo,
        tipo_cp,
        serie,
        numero,
        extension=extension,
        subcarpeta=subcarpeta,
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    logger.info("Archivo guardado ruta=%s bytes=%s", relativa(destino), len(contenido))
    return destino


def relativa(destino: Path) -> str:
    """Ruta relativa a la raíz, que es la forma en que se guarda en Mongo.

    Guardar la absoluta ataría la base al punto de montaje: mover el volumen
    invalidaría todos los punteros.
    """
    try:
        return destino.resolve().relative_to(raiz().resolve()).as_posix()
    except ValueError:
        return destino.as_posix()


def absoluta(ruta_relativa: str) -> Path:
    """Inversa de `relativa`, con la misma comprobación de contención."""
    destino = (raiz() / ruta_relativa).resolve()
    base = raiz().resolve()
    if not destino.is_relative_to(base):
        raise ValueError(f"La ruta guardada se sale del almacén: {ruta_relativa}")
    return destino


def listar(ruc: str, libro: Libro, periodo: str) -> list[Path]:
    """PDFs ya descargados de ese periodo, ordenados por ruta."""
    base = raiz_periodo(ruc, libro, periodo)
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.pdf") if p.is_file())
