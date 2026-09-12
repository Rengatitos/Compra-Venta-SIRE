import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.v1.deps import empresa_actual, empresa_id, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.repositories._mongo import monto_a_float
from app.schemas.comprobante import ComprobanteResponse, ComprobanteUpdate
from app.schemas.generic import MessageResponse
from app.services import export_service, plantilla_excel, propuesta_service
from app.services.comprobante_service import serializar, serializar_lote
from app.services.sunat import resumen_rce
from app.services.sunat.auth import ErrorSunat

router = APIRouter()
logger = logging.getLogger(__name__)

MEDIA_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _asegurar_periodo(db, empresa: str, periodo: str) -> None:
    if not await repo_periodos.obtener(db, empresa, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")


@router.get("", response_model=list[ComprobanteResponse], summary="Listar comprobantes")
async def listar_comprobantes(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro | None = Query(None, description="Filtrar por libro"),
    limit: int = 100,
    skip: int = 0,
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    filas = await repo_comprobantes.listar(
        db, empresa, periodo, libro=libro, skip=skip, limit=limit
    )
    return serializar_lote(filas)


@router.get("/incompletos", response_model=list[ComprobanteResponse])
async def incompletos(
    periodo: str = Depends(periodo_valido), empresa: str = Depends(empresa_id),
    libro: Libro = Query(...), db=Depends(get_db),
):
    from app.services.revision_comprobantes import incompleto

    await _asegurar_periodo(db, empresa, periodo)
    resultado = []
    skip = 0
    while True:
        filas = await repo_comprobantes.listar(db, empresa, periodo, libro=libro, skip=skip, limit=500)
        for fila in filas:
            visible = {**fila, **serializar(fila)}
            if incompleto(visible):
                resultado.append(visible)
        if len(filas) < 500:
            break
        skip += 500
    return resultado


@router.get("/anulados-sunat", response_model=list[ComprobanteResponse])
async def anulados_sunat(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro = Query(...),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    return serializar_lote(await repo_comprobantes.listar_anulados_sunat(db, empresa, periodo, libro))


@router.get("/cobertura-sunat", response_model=dict[str, int])
async def cobertura_sunat(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro = Query(...),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    return await repo_comprobantes.cobertura_sunat(db, empresa, periodo, libro)


@router.get("/export", summary="Exportar todos los comprobantes del periodo")
async def exportar_lote(
    periodo: str = Depends(periodo_valido),
    empresa_doc: dict = Depends(empresa_actual),
    formato: str = Query("excel", pattern="^(excel|pdf)$"),
    libro: Libro | None = Query(
        None, description="Obligatorio para `formato=excel`; filtro opcional para el PDF"
    ),
    destino: str | None = Query(
        None,
        description="Destino de compras: 'dg' (gravado), 'dng' (no gravado/costo), 'dgng' o 'auto'",
    ),
    db=Depends(get_db),
):
    empresa = str(empresa_doc["_id"])
    await _asegurar_periodo(db, empresa, periodo)

    # Un archivo de la plantilla oficial es de un solo libro: sin `libro` no hay
    # forma de saber qué hoja del formato Contasis generar.
    if formato == "excel" and libro is None:
        raise HTTPException(
            status_code=400,
            detail="Indica el libro (compras o ventas) para exportar en Excel",
        )

    # El Registro de Compras se reconstruye siempre desde el ZIP oficial del
    # ticket. Así el botón no exporta una instantánea vieja de Mongo.
    if formato == "excel" and libro == Libro.COMPRAS:
        try:
            sincronizacion = await propuesta_service.sincronizar_ticket_rce(
                db, empresa_doc, periodo
            )
        except ErrorSunat as exc:
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo actualizar la propuesta mediante ticket SUNAT: {exc}",
            ) from exc
        logger.info(
            "Ticket RCE importado antes de exportar periodo=%s ticket=%s filas=%s",
            periodo,
            sincronizacion.get("ticket"),
            sincronizacion.get("filas_archivo"),
        )

    filas = await repo_comprobantes.listar(db, empresa, periodo, libro=libro, limit=5000)
    if not filas:
        raise HTTPException(status_code=404, detail="No hay comprobantes en el periodo indicado")

    datos = serializar_lote(filas)

    if formato == "excel":
        destino_resuelto = destino
        if libro == Libro.COMPRAS and (destino is None or destino == "auto"):
            # Auto-detección: si la empresa en este periodo (o en su histórico reciente)
            # solo tiene ventas exoneradas/inafectas, todas sus compras corresponden
            # a 'dng' (adquisiciones gravadas destinadas a operaciones no gravadas).
            ventas_periodo = await repo_comprobantes.listar(
                db, empresa, periodo, libro=Libro.VENTAS, limit=50
            )
            if not ventas_periodo:
                ventas_periodo = await repo_comprobantes.listar(
                    db, empresa, None, libro=Libro.VENTAS, limit=50
                )
            if ventas_periodo and all(
                (monto_a_float(v.get("base_imponible")) == 0)
                and (monto_a_float(v.get("total")) > 0)
                for v in ventas_periodo
            ):
                destino_resuelto = "dng"

        if libro == Libro.COMPRAS:
            try:
                resumen_original = await resumen_rce.obtener(db, empresa_doc, periodo)
                control_global = await resumen_rce.obtener_control(db, empresa_doc, periodo)
            except ErrorSunat as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            conciliacion = resumen_rce.conciliar(resumen_original, datos, control_global)
            logger.info(
                "Conciliación RCE periodo=%s cantidad_sunat=%s cantidad_procesada=%s "
                "monedas=%s sin_tc=%s totales_pen=%s total_sire_original=%s",
                periodo,
                resumen_original["cantidad"],
                len(datos),
                conciliacion["procesamiento_pen"]["cantidad_por_moneda"],
                len(conciliacion["procesamiento_pen"]["comprobantes_sin_tc"]),
                conciliacion["procesamiento_pen"]["totales_pen"],
                resumen_original["total_original"],
            )
            if not conciliacion["cantidad_coincide"]:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "mensaje": (
                            "No se puede exportar un Registro de Compras incompleto. "
                            "Descargue e importe la propuesta mediante ticket SUNAT"
                        ),
                        "cantidad_propuesta_sunat": resumen_original["cantidad"],
                        "cantidad_procesada": len(datos),
                        "diferencia": resumen_original["cantidad"] - len(datos),
                        "advertencias": conciliacion["advertencias"],
                    },
                )

        nombre = f"registro_{libro.value}_{periodo}.xlsx"
        try:
            archivo = plantilla_excel.excel_plantilla(datos, libro, destino=destino_resuelto)
        except plantilla_excel.ErrorTipoCambio as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "mensaje": (
                        "No se puede exportar: hay comprobantes en moneda extranjera "
                        "sin tipo de cambio SUNAT"
                    ),
                    "comprobantes_sin_tc": exc.pendientes,
                },
            ) from exc
        return StreamingResponse(
            archivo,
            media_type=MEDIA_EXCEL,
            headers={"Content-Disposition": f"attachment; filename={nombre}"},
        )

    return StreamingResponse(
        export_service.pdf_de_lote(datos),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=comprobantes_{periodo}.pdf"},
    )


@router.get("/conciliacion-rce", summary="Conciliar compras con el resumen oficial del SIRE")
async def conciliacion_rce(
    periodo: str = Depends(periodo_valido),
    empresa_doc: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    empresa = str(empresa_doc["_id"])
    await _asegurar_periodo(db, empresa, periodo)
    filas = await repo_comprobantes.listar(
        db, empresa, periodo, libro=Libro.COMPRAS, limit=5000
    )
    try:
        resumen_original = await resumen_rce.obtener(db, empresa_doc, periodo)
        control_global = await resumen_rce.obtener_control(db, empresa_doc, periodo)
    except ErrorSunat as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return resumen_rce.conciliar(
        resumen_original, serializar_lote(filas), control_global
    )


@router.get(
    "/{serie_numero}", response_model=ComprobanteResponse, summary="Consultar comprobante"
)
async def obtener_comprobante(
    serie_numero: str,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro | None = Query(None, description="Desambigua si existe en ambos libros"),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero, libro)
    if not fila:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    return serializar(fila)


@router.patch(
    "/{serie_numero}", response_model=MessageResponse, summary="Editar la descripción del análisis"
)
async def actualizar_comprobante(
    serie_numero: str,
    datos: ComprobanteUpdate,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    libro: Libro | None = Query(None, description="Desambigua si existe en ambos libros"),
    db=Depends(get_db),
):
    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero, libro)
    if not fila:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    if datos.descripcion is not None:
        await repo_comprobantes.guardar_glosa(db, fila["_id"], datos.descripcion)

    await repo_comprobantes.guardar_campos_contraparte(db, fila["_id"], {
        campo: getattr(datos, campo).strip()
        for campo in ("razon_social", "documento_contraparte")
        if getattr(datos, campo) is not None
    })

    return {"mensaje": "Comprobante actualizado correctamente"}


@router.get("/{serie_numero}/export", summary="Exportar un comprobante")
async def exportar_comprobante(
    serie_numero: str,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    formato: str = Query("pdf", pattern="^(excel|pdf)$"),
    libro: Libro | None = Query(None, description="Desambigua si existe en ambos libros"),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)

    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero, libro)
    if not fila:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    datos = serializar(fila)

    if formato == "excel":
        return StreamingResponse(
            export_service.excel_de_comprobante(datos),
            media_type=MEDIA_EXCEL,
            headers={
                "Content-Disposition": f"attachment; filename=comprobante_{serie_numero}.xlsx"
            },
        )

    return StreamingResponse(
        export_service.pdf_de_comprobante(datos),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=comprobante_{serie_numero}.pdf"},
    )
