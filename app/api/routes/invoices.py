from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
import json
from pydantic import BaseModel
from typing import List, Optional
from app.db.database import get_db
from app.core.auth import require_same_user
from app.schemas.invoice import InvoiceResponse
from app.schemas.generic import MessageResponse
from app.services.invoice_service import dedupe_by_reference, parse_metadata, serialize_factura
from app.services.export_service import (
    generate_excel_from_invoice,
    generate_pdf_from_invoice,
    generate_excel_from_invoices_batch,
    generate_pdf_from_invoices_batch,
)

router = APIRouter()

class UpdateFacturaModel(BaseModel):
    Descripcion: Optional[str] = None


@router.get("/", response_model=List[InvoiceResponse])
async def list_invoices(user_id: str, periodo: str, limit: int = 100, skip: int = 0, db=Depends(get_db), user=Depends(require_same_user)):
    periods_col = db["periodos"]
    periodo_obj = await periods_col.find_one({"user_id": user_id, "periodo": periodo})
    if not periodo_obj:
        raise HTTPException(status_code=404, detail="Periodo no encontrado para este usuario")

    facturas_col = db["facturas"]
    cursor = facturas_col.find({"user_id": user_id, "periodo": periodo}).skip(skip).limit(limit)
    rows = await cursor.to_list(length=limit)
    serialized = [serialize_factura(row) for row in rows]
    return dedupe_by_reference(serialized)


@router.get("/export/batch")
@router.get("/batch/export")
async def export_invoices_batch(user_id: str, periodo: str, format: str = "excel", db=Depends(get_db), user=Depends(require_same_user)):
    periods_col = db["periodos"]
    periodo_obj = await periods_col.find_one({"user_id": user_id, "periodo": periodo})
    if not periodo_obj:
        raise HTTPException(status_code=404, detail="Periodo no encontrado para este usuario")

    facturas_col = db["facturas"]
    rows = await facturas_col.find({"user_id": user_id, "periodo": periodo}).to_list(length=5000)
    if not rows:
        raise HTTPException(status_code=404, detail="No hay facturas en el periodo indicado")

    invoices_data = dedupe_by_reference([serialize_factura(row) for row in rows])

    if format == "excel":
        excel_file = generate_excel_from_invoices_batch(invoices_data)
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=facturas_{periodo}.xlsx"},
        )
    elif format == "pdf":
        pdf_file = generate_pdf_from_invoices_batch(invoices_data)
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=facturas_{periodo}.pdf"},
        )
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado, usa 'pdf' o 'excel'")


@router.get("/{id_factura}", response_model=InvoiceResponse)
async def get_invoice(user_id: str, periodo: str, id_factura: str, db=Depends(get_db), user=Depends(require_same_user)):
    periods_col = db["periodos"]
    periodo_obj = await periods_col.find_one({"user_id": user_id, "periodo": periodo})
    if not periodo_obj:
        raise HTTPException(status_code=404, detail="Periodo no encontrado para este usuario")

    facturas_col = db["facturas"]
    row = await facturas_col.find_one({"user_id": user_id, "periodo": periodo, "serie_numero": id_factura})
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    return serialize_factura(row)


@router.patch("/{id_factura}", response_model=MessageResponse)
async def update_invoice(user_id: str, periodo: str, id_factura: str, data: UpdateFacturaModel, db=Depends(get_db), user=Depends(require_same_user)):
    facturas_col = db["facturas"]
    row = await facturas_col.find_one({"user_id": user_id, "periodo": periodo, "serie_numero": id_factura})
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    meta = parse_metadata(row)
    if data.Descripcion is not None:
        meta["Descripcion"] = data.Descripcion

    original_meta = row.get("metadata_procesada")
    if isinstance(original_meta, str):
        updated_meta = json.dumps(meta, ensure_ascii=False)
    else:
        updated_meta = meta

    await facturas_col.update_one(
        {"_id": row["_id"]},
        {"$set": {"metadata_procesada": updated_meta}}
    )

    return {"message": "Factura actualizada correctamente"}


@router.get("/{id_factura}/export")
async def export_invoice(user_id: str, periodo: str, id_factura: str, format: str = "pdf", db=Depends(get_db), user=Depends(require_same_user)):
    periods_col = db["periodos"]
    periodo_obj = await periods_col.find_one({"user_id": user_id, "periodo": periodo})
    if not periodo_obj:
        raise HTTPException(status_code=404, detail="Periodo no encontrado para este usuario")

    facturas_col = db["facturas"]
    row = await facturas_col.find_one({"user_id": user_id, "periodo": periodo, "serie_numero": id_factura})
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")

    factura_data = serialize_factura(row)

    if format == "excel":
        excel_file = generate_excel_from_invoice(factura_data)
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=factura_{id_factura}.xlsx"}
        )
    elif format == "pdf":
        pdf_file = generate_pdf_from_invoice(factura_data)
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=factura_{id_factura}.pdf"}
        )
    else:
        raise HTTPException(status_code=400, detail="Formato no soportado, usa 'pdf' o 'excel'")
