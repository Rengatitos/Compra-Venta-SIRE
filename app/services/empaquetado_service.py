"""Archivos finales de una solicitud: Excel y comprobantes de cada empresa y
periodo, organizados en carpetas dentro de un ZIP.

    DESCARGA_2026-09-27.zip
    ├── 20123456789_2026-08_2026-09-27/
    │   ├── Ventas/Reporte_Ventas.xlsx
    │   ├── Compras/Reporte_Compras.xlsx
    │   └── Comprobantes/{Facturas, Boletas, Notas de crédito, Notas de débito, Otros}/
    └── …

La carpeta es `RUC_AAAA-MM_AAAA-MM-DD`: periodo procesado y día (en Lima) de la
última descarga SIRE. Los PDF se leen de donde ya los guardó el scraping
(`almacen_pdf`) y se escriben directamente en el ZIP, sin copiarlos antes a otra
carpeta. El Excel es el de la plantilla oficial (`plantilla_excel`), generado
desde lo que hay en Mongo: no se vuelve a llamar a SUNAT.
"""

from __future__ import annotations

import asyncio
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.domain.comprobante import Libro
from app.domain.solicitudes import nombre_carpeta
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import empresas as repo_empresas
from app.repositories import jobs as repo_jobs
from app.services import almacen_pdf, destino_compras, pagos_vouchers
from app.services.comprobante_service import serializar_lote
from app.services.plantilla_excel import ErrorTipoCambio, excel_plantilla

logger = logging.getLogger(__name__)

MAX_COMPROBANTES = 5000
CARPETA_LIBRO = {Libro.VENTAS: "Ventas", Libro.COMPRAS: "Compras"}
ARCHIVO_LIBRO = {Libro.VENTAS: "Reporte_Ventas.xlsx", Libro.COMPRAS: "Reporte_Compras.xlsx"}
PREFIJO_LIBRO = {Libro.VENTAS: "VENTA", Libro.COMPRAS: "COMPRA"}
# Mismas categorías que `almacen_pdf.CARPETAS_POR_TIPO`, con nombre legible.
CARPETA_COMPROBANTES = {
    "facturas": "Facturas",
    "boletas": "Boletas",
    "notas_credito": "Notas de crédito",
    "notas_debito": "Notas de débito",
    almacen_pdf.CARPETA_POR_DEFECTO: "Otros",
}
# Las que siempre aparecen, aunque estén vacías: el contador espera navegar la
# misma estructura en todas las empresas.
CARPETAS_FIJAS = ("Facturas", "Boletas", "Otros")
_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9._-]+")


def raiz_solicitud(solicitud_id: str) -> Path:
    return almacen_pdf.raiz() / "solicitudes" / solicitud_id


def _limpio(valor: Any) -> str:
    return _NO_PERMITIDO.sub("", str(valor or "")) or "SN"


@dataclass
class Carpeta:
    """Lo que va en la carpeta de un item, ya reunido desde Mongo y el disco."""

    nombre: str
    archivos: list[tuple[str, bytes | Path]] = field(default_factory=list)
    observaciones: list[str] = field(default_factory=list)
    pdfs: int = 0
    sin_pdf: int = 0


async def reunir(db, item: dict[str, Any]) -> Carpeta:
    ruc, periodo = item["ruc"], item["periodo"]
    ultima = await repo_jobs.ultima_sincronizacion_sire(db, ruc, periodo)
    carpeta = Carpeta(nombre_carpeta(ruc, periodo, ultima))
    carpeta.observaciones.extend(item.get("observaciones") or [])
    if ultima is None:
        carpeta.observaciones.append(
            "No hay una descarga SIRE completada de este periodo: la fecha de la carpeta es la "
            "de hoy."
        )

    empresa = await repo_empresas.obtener_por_ruc(db, ruc)
    if not empresa:
        carpeta.observaciones.append("La empresa ya no existe en Sire.")
        return carpeta
    empresa_id = str(empresa["_id"])

    usados: set[str] = set()
    for libro in (Libro.VENTAS, Libro.COMPRAS):
        filas = await repo_comprobantes.listar(
            db, empresa_id, periodo, libro=libro, limit=MAX_COMPROBANTES
        )
        destino = (
            await destino_compras.detectar(db, empresa_id, periodo)
            if libro is Libro.COMPRAS
            else None
        )
        datos = serializar_lote(filas)
        sin_comprobante = await pagos_vouchers.adjuntar_pagos(
            db, empresa_id, periodo, datos, libro.value
        )
        try:
            excel = await asyncio.to_thread(
                excel_plantilla, datos, libro, destino, sin_comprobante
            )
        except ErrorTipoCambio as exc:
            carpeta.observaciones.append(
                f"{CARPETA_LIBRO[libro]}: no se generó el Excel, {exc}. Registra el tipo de "
                "cambio y vuelve a procesar el periodo."
            )
        else:
            carpeta.archivos.append(
                (f"{CARPETA_LIBRO[libro]}/{ARCHIVO_LIBRO[libro]}", excel.getvalue())
            )
        if not filas:
            carpeta.observaciones.append(
                f"{CARPETA_LIBRO[libro]}: SUNAT no tiene comprobantes en el periodo."
            )

        for fila in filas:
            ruta = (fila.get("pdf_sunat") or {}).get("ruta")
            pdf = _pdf_existente(ruta)
            if pdf is None:
                carpeta.sin_pdf += 1
                continue
            emisor = fila.get("documento_contraparte") if libro is Libro.COMPRAS else ruc
            tipo = CARPETA_COMPROBANTES.get(
                almacen_pdf.carpeta_de_tipo(fila.get("tipo_cp")), "Otros"
            )
            base = f"{PREFIJO_LIBRO[libro]}_{_limpio(emisor)}_{_limpio(fila.get('serie_numero'))}"
            nombre = f"Comprobantes/{tipo}/{base}.pdf"
            repetido = 2
            while nombre in usados:
                nombre = f"Comprobantes/{tipo}/{base}_{repetido}.pdf"
                repetido += 1
            usados.add(nombre)
            carpeta.archivos.append((nombre, pdf))
            carpeta.pdfs += 1

    if carpeta.sin_pdf:
        carpeta.observaciones.append(
            f"{carpeta.sin_pdf} comprobantes sin PDF descargado de SUNAT."
        )
    return carpeta


def _pdf_existente(ruta: str | None) -> Path | None:
    if not ruta:
        return None
    try:
        pdf = almacen_pdf.absoluta(ruta)
    except ValueError:
        return None
    return pdf if pdf.is_file() else None


def _escribir(destino: Path, carpetas: list[Carpeta]) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_suffix(".parcial")
    with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zf:
        for carpeta in carpetas:
            for fija in CARPETAS_FIJAS:
                zf.writestr(f"{carpeta.nombre}/Comprobantes/{fija}/", "")
            for nombre, contenido in carpeta.archivos:
                arcname = f"{carpeta.nombre}/{nombre}"
                if isinstance(contenido, Path):
                    zf.write(contenido, arcname=arcname)
                else:
                    zf.writestr(arcname, contenido)
            if carpeta.observaciones:
                zf.writestr(
                    f"{carpeta.nombre}/observaciones.txt",
                    "\r\n".join(carpeta.observaciones) + "\r\n",
                )
    # Se renombra al final: un ZIP a medias nunca tiene el nombre definitivo.
    temporal.replace(destino)
    return destino.stat().st_size


async def armar_zip(db, items: list[dict[str, Any]], destino: Path) -> dict[str, Any]:
    """Escribe el ZIP de esos items en `destino` y resume lo que lleva."""
    carpetas = [await reunir(db, item) for item in items]
    tamano = await asyncio.to_thread(_escribir, destino, carpetas)
    logger.info(
        "ZIP %s: %s carpetas, %s PDF, %s bytes", destino.name, len(carpetas),
        sum(c.pdfs for c in carpetas), tamano,
    )
    return {
        "archivo": destino.name,
        "bytes": tamano,
        "generado_en": datetime.now(UTC),
        "carpetas": [
            {
                "nombre": c.nombre,
                "pdfs": c.pdfs,
                "sin_pdf": c.sin_pdf,
                "observaciones": c.observaciones,
            }
            for c in carpetas
        ],
    }
