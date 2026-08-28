
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.v1.deps import empresa_id, periodo_valido
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.schemas.comprobante import ComprobanteResponse, ComprobanteUpdate
from app.schemas.generic import MessageResponse
from app.services import export_service
from app.services.comprobante_service import serializar, serializar_lote

router = APIRouter()

MEDIA_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _asegurar_periodo(db, empresa: str, periodo: str) -> None:
    if not await repo_periodos.obtener(db, empresa, periodo):
        raise HTTPException(status_code=404, detail="Periodo no encontrado para esta empresa")


def _filtrar_por_libro(filas: list[dict], libro: Libro | None) -> list[dict]:
    if libro is None:
        return filas
    return [f for f in filas if f.get("libro") == libro.value]


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
    filas = await repo_comprobantes.listar(db, empresa, periodo, skip=skip, limit=limit)
    return serializar_lote(_filtrar_por_libro(filas, libro))


@router.get("/export", summary="Exportar todos los comprobantes del periodo")
async def exportar_lote(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    formato: str = Query("excel", pattern="^(excel|pdf)$"),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)

    filas = await repo_comprobantes.listar(db, empresa, periodo, limit=5000)
    if not filas:
        raise HTTPException(status_code=404, detail="No hay comprobantes en el periodo indicado")

    datos = serializar_lote(filas)

    if formato == "excel":
        return StreamingResponse(
            export_service.excel_de_lote(datos),
            media_type=MEDIA_EXCEL,
            headers={"Content-Disposition": f"attachment; filename=comprobantes_{periodo}.xlsx"},
        )

    return StreamingResponse(
        export_service.pdf_de_lote(datos),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=comprobantes_{periodo}.pdf"},
    )


@router.get(
    "/{serie_numero}", response_model=ComprobanteResponse, summary="Consultar comprobante"
)
async def obtener_comprobante(
    serie_numero: str,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)
    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero)
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
    db=Depends(get_db),
):
    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero)
    if not fila:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    if datos.descripcion is not None:
        metadata = dict(fila.get("metadata_procesada") or {})
        metadata["descripcion"] = datos.descripcion
        await repo_comprobantes.guardar_metadata(db, fila["_id"], metadata)

    return {"mensaje": "Comprobante actualizado correctamente"}


@router.get("/{serie_numero}/export", summary="Exportar un comprobante")
async def exportar_comprobante(
    serie_numero: str,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    formato: str = Query("pdf", pattern="^(excel|pdf)$"),
    db=Depends(get_db),
):
    await _asegurar_periodo(db, empresa, periodo)

    fila = await repo_comprobantes.obtener(db, empresa, periodo, serie_numero)
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
