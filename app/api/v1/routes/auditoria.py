"""Reporte para el auditor.

El auditor pidió tres cosas: la glosa detallada de cada comprobante, los PDFs
en ZIP y una tabla comparativa **con fuentes**. Las dos primeras ya existen (el
RAG produce la glosa, `routes/pdfs.py` sirve el ZIP); esta ruta arma la tercera.

Lo que la hace un reporte de auditoría y no un listado más es el bloque
`fuentes`: por cada comprobante dice de dónde salió cada dato. Sin eso el
auditor no puede distinguir un importe que declaró SUNAT en la propuesta de uno
que se leyó del detalle del portal o del PDF, que es justo lo que tiene que
poder rastrear.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import empresa_actual, empresa_id, libro_valido, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.schemas.auditoria import ReporteResponse
from app.services import almacen_pdf
from app.services.comprobante_service import serializar

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILAS = 5000

# De dónde puede venir un dato. Son las tres fuentes que hoy alimentan un
# comprobante, en orden de cercanía al documento original.
FUENTE_PROPUESTA = "propuesta_sire"
FUENTE_PORTAL = "detalle_portal_sol"
FUENTE_PDF = "pdf_descargado"


def _fuentes(documento: dict) -> list[str]:
    """Qué respalda a este comprobante, de menos a más cerca del original."""
    fuentes = []
    # Todo comprobante entró por la propuesta: es lo que lo hizo existir.
    if documento.get("origen") == "sire":
        fuentes.append(FUENTE_PROPUESTA)
    if documento.get("detalle_sunat"):
        fuentes.append(FUENTE_PORTAL)
    if (documento.get("pdf_sunat") or {}).get("ruta"):
        fuentes.append(FUENTE_PDF)
    return fuentes


def _a_numero(valor: object) -> float | None:
    """Un importe del popup a número, o `None` si la celda no lo es.

    El portal devuelve texto tal cual sale de la tabla: `'.00'`, `'1,234.56'`,
    celdas con espacios. Es el mismo saneado que hace `detalleSunat.ts` en el
    frontend.
    """
    texto = str(valor or "").replace(",", "").replace(" ", "").strip()
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def _importe_del_detalle(detalle: list) -> float | None:
    """Suma de los valores de venta de las líneas leídas del portal.

    Es la columna que hace comparable la tabla: enfrenta el total que declaró
    SUNAT en la propuesta con la suma de lo que dice el comprobante línea a
    línea. Contra los datos reales, esa suma cuadra con `total` al céntimo, así
    que las diferencias que aparecen son de verdad.

    El campo es `valor_venta`, el nombre que le pone `_parsear_filas` a la
    columna del portal (`app/services/scraping_sunat.py::_COLUMNAS`). El
    `icbper` no se suma aparte: ya viene incluido en el total.

    Devuelve `None` cuando no hay ninguna línea con importe legible. Eso **no**
    es un cero: significa que no hay con qué comparar, y confundirlos hacía que
    todo comprobante con detalle saliera descuadrado por su importe completo.
    """
    if not detalle:
        return None

    total = 0.0
    encontrados = 0
    for linea in detalle:
        if not isinstance(linea, dict):
            continue
        importe = _a_numero(linea.get("valor_venta"))
        if importe is None:
            continue
        total += importe
        encontrados += 1

    return round(total, 2) if encontrados else None


def _fila(documento: dict) -> dict:
    datos = serializar(documento)
    pdf = documento.get("pdf_sunat") or {}
    analisis = datos.get("analisis") or {}
    rag = analisis.get("rag") or {}
    detalle = datos.get("detalle_sunat") or []
    importe_detalle = _importe_del_detalle(detalle)
    total = datos.get("total") or 0.0

    return {
        "serie_numero": datos["serie_numero"],
        "tipo_cp": datos["tipo_cp"],
        "tipo_cp_descripcion": datos["tipo_cp_descripcion"],
        "fecha_emision": datos["fecha_emision"],
        "documento_contraparte": datos["documento_contraparte"],
        "razon_social": datos["razon_social"],
        "moneda": datos["moneda"],
        # Lo que declara el registro.
        "base_imponible": datos["base_imponible"],
        "igv": datos["igv"],
        "total": total,
        # Lo que se pudo leer del comprobante en sí.
        "importe_detalle": importe_detalle,
        # `None` cuando no hay con qué comparar, para que el frontend no pinte
        # una diferencia inventada de cero.
        "diferencia": None if importe_detalle is None else round(importe_detalle - total, 2),
        "lineas_detalle": len(detalle),
        "detalle_sunat": detalle,
        # La glosa: lo primero que pidió el auditor.
        "glosa": rag.get("glosa") or analisis.get("descripcion") or "",
        "cuenta_base": rag.get("cuenta_base") or analisis.get("cuenta_contable") or "",
        "cuenta_total": rag.get("cuenta_total") or "",
        "observaciones": analisis.get("observaciones") or "",
        # Las fuentes: lo que hace rastreable cada fila.
        "fuentes": _fuentes({**documento, "detalle_sunat": detalle}),
        "pdf": pdf.get("ruta") or None,
    }


@router.get(
    "/reporte",
    response_model=ReporteResponse,
    summary="Tabla comparativa con glosas y fuentes para el auditor",
)
async def obtener_reporte(
    periodo: str = Depends(periodo_valido),
    libro: Libro = Depends(libro_valido),
    empresa: dict = Depends(empresa_actual),
    empresa_pk: str = Depends(empresa_id),
    limit: int = Query(MAX_FILAS, ge=1, le=MAX_FILAS),
    db=Depends(get_db),
):
    if not await repo_periodos.obtener(db, empresa_pk, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")

    documentos = await repo_comprobantes.listar(
        db, empresa_pk, periodo, libro=libro, limit=limit
    )
    filas = [_fila(documento) for documento in documentos]

    con_pdf = sum(1 for fila in filas if fila["pdf"])
    con_detalle = sum(1 for fila in filas if fila["lineas_detalle"])
    con_glosa = sum(1 for fila in filas if fila["glosa"])
    # Sólo se cuenta como descuadre lo que se pudo comparar. Un comprobante sin
    # detalle no cuadra ni descuadra: falta el dato, y decir "0 diferencias"
    # cuando no hay nada comparado es peor que no decir nada.
    comparables = [fila for fila in filas if fila["diferencia"] is not None]
    descuadrados = [fila for fila in comparables if abs(fila["diferencia"]) > 0.01]

    return {
        "periodo": periodo,
        "libro": libro.value,
        "filas": filas,
        "resumen": {
            "comprobantes": len(filas),
            "con_pdf": con_pdf,
            "con_detalle": con_detalle,
            "con_glosa": con_glosa,
            "comparables": len(comparables),
            "descuadrados": len(descuadrados),
            "total_registro": round(sum(fila["total"] for fila in filas), 2),
        },
        # El ZIP lo sirve `routes/pdfs.py`; aquí sólo se dice si hay algo que
        # descargar, para no ofrecer un botón que va a responder 404.
        "zip_disponible": bool(almacen_pdf.listar(empresa["ruc"], libro, periodo)),
    }
