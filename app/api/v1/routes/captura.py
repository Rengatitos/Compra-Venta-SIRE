"""API de inventario documental usando la sesión y empresa existentes."""

import asyncio
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pymongo.errors import DuplicateKeyError

from app.core.auth import empresa_autenticada
from app.core.captura_config import captura_settings
from app.db.database import get_db
from app.domain.captura.period import parse_period
from app.domain.captura.validation import match_score
from app.repositories import captura as repo
from app.schemas.captura import (
    ActionInput,
    DocumentUpdate,
    MovePeriodInput,
    PeriodInput,
    PhoneInput,
)
from app.services.captura.ingestion import receive_webhook
from app.services.captura.review import ExportService, mutate, require_document
from app.services.captura.storage import inspect_file, storage
from app.services.captura.twilio import validate_webhook

router = APIRouter(prefix="/captura", tags=["Captura documental"])


def company_id(company: dict = Depends(empresa_autenticada)) -> str:
    return str(company["_id"])


@router.post("/whatsapp")
async def whatsapp(request: Request, db=Depends(get_db)):
    from twilio.twiml.messaging_response import MessagingResponse

    data = await validate_webhook(request, captura_settings())
    message = await receive_webhook(db, data)
    response = MessagingResponse()
    response.message(message)
    return Response(str(response), media_type="application/xml")


@router.get("/phones")
async def phones(company: str = Depends(company_id), db=Depends(get_db)):
    rows = await repo.collection(db, "phones").find({"company_id": company}).to_list(100)
    return [{"id": row["_id"], "phone": row["phone"], "active": row["active"]} for row in rows]


@router.post("/phones")
async def authorize_phone(body: PhoneInput, company: str = Depends(company_id), db=Depends(get_db)):
    async def apply(tx):
        # Serializa cambios de autorización para una misma empresa.
        await repo.collection(db, "company_settings").update_one(
            {"_id": company}, {"$inc": {"phone_revision": 1}}, upsert=True, session=tx
        )
        existing = await repo.collection(db, "phones").find_one({"phone": body.phone}, session=tx)
        if existing and existing["company_id"] != company:
            raise HTTPException(409, "Teléfono ya asociado a otra empresa")
        # Un teléfono activo inicialmente; la colección admite ampliarlo después.
        if body.active:
            await repo.collection(db, "phones").update_many(
                {"company_id": company}, {"$set": {"active": False}}, session=tx
            )
        await repo.collection(db, "phones").update_one(
            {"phone": body.phone},
            {
                "$set": {"company_id": company, "active": body.active, "updated_at": repo.now()},
                "$setOnInsert": {"_id": uuid4().hex},
            },
            upsert=True,
            session=tx,
        )
        await repo.audit(
            db,
            company,
            "phone",
            "EMPRESA:" + company,
            "AUTHORIZE_PHONE",
            new={"last4": body.phone[-4:], "active": body.active},
            session=tx,
        )

    try:
        await repo.transaction(db, apply)
    except DuplicateKeyError:
        raise HTTPException(409, "Teléfono ya asociado") from None
    return {"phone": body.phone, "active": body.active}


@router.get("/documents")
async def documents(
    company: str = Depends(company_id),
    db=Depends(get_db),
    period: str | None = None,
    status: str | None = None,
    type: str | None = None,
    batch_id: str | None = None,
    q: str = "",
    observed: bool = False,
    duplicates: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    sort: str = Query("received_at", pattern="^(received_at|document_date|accounting_period)$"),
    order: int = Query(-1, ge=-1, le=1),
):
    query = {"company_id": company}
    for key, value in [
        ("accounting_period", period),
        ("status", status),
        ("document_type", type),
        ("batch_id", batch_id),
    ]:
        if value:
            query[key] = value
    if observed:
        query["status"] = {"$in": ["NEEDS_REVIEW", "FAILED"]}
    if duplicates:
        query["possible_duplicate"] = True
    if q:
        pattern = {"$regex": re.escape(q[:100]), "$options": "i"}
        query["search_text"] = pattern
    rows = (
        await repo.collection(db, "documents")
        .find(query)
        .sort([(sort, -1 if order <= 0 else 1), ("_id", 1)])
        .skip((page - 1) * limit)
        .limit(limit)
        .to_list(limit)
    )
    return {
        "items": [repo.public(row) for row in rows],
        "total": await repo.collection(db, "documents").count_documents(query),
        "page": page,
    }


@router.post("/documents", status_code=202)
async def upload(
    file: UploadFile = File(...),
    batch_id: str | None = Form(None),
    company: str = Depends(company_id),
    db=Depends(get_db),
):
    settings = captura_settings()
    content = await file.read(settings.MAX_FILE_SIZE_MB * 1024 * 1024 + 1)
    try:
        info = await asyncio.to_thread(inspect_file, content, settings)
    except Exception:
        raise HTTPException(
            422, "Archivo inválido, excede límites o no es JPG/PNG/WebP/PDF"
        ) from None
    key = await asyncio.to_thread(storage(settings).put, content)
    document = repo.new_document(
        company,
        "WEB",
        storage_key=key,
        mime=info["mime"],
        file_hash=info["sha256"],
        file_size=info["size"],
        batch_id=batch_id,
    )

    async def apply(tx):
        if batch_id:
            batch = await repo.get(db, "batches", company, batch_id, tx)
            if not batch or batch["status"] != "RECEIVING":
                raise HTTPException(409, "Lote no disponible para recepción")
            if batch["received_count"] >= settings.MAX_BATCH_DOCUMENTS:
                raise HTTPException(409, "Lote lleno")
            document["target_period"] = batch["accounting_period"]
            await repo.collection(db, "batches").update_one(
                {"_id": batch_id}, {"$inc": {"received_count": 1}}, session=tx
            )
        await repo.collection(db, "documents").insert_one(document, session=tx)
        await repo.audit(db, company, document["_id"], "EMPRESA:" + company, "UPLOAD", session=tx)

    await repo.transaction(db, apply)
    return repo.public(document)


@router.get("/documents/{identifier}")
async def document_detail(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    document = await require_document(db, company, identifier)
    history = (
        await repo.collection(db, "audit")
        .find({"company_id": company, "document_id": identifier})
        .sort("timestamp", -1)
        .limit(100)
        .to_list(100)
    )
    matches = (
        await repo.collection(db, "matches")
        .find({"company_id": company, "documents": identifier})
        .limit(50)
        .to_list(50)
    )
    return {
        **repo.public(document),
        "audit": [repo.public(row) for row in history],
        "matches": [repo.public(row) for row in matches],
    }


@router.get("/documents/{identifier}/file")
async def original(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    document = await require_document(db, company, identifier)
    if not document.get("storage_key"):
        raise HTTPException(404, "Archivo aún no disponible")
    content = await asyncio.to_thread(storage(captura_settings()).read, document["storage_key"])
    return Response(
        content,
        media_type=document["mime"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{identifier}"',
        },
    )


@router.patch("/documents/{identifier}")
async def edit(
    identifier: str, body: DocumentUpdate, company: str = Depends(company_id), db=Depends(get_db)
):
    return await mutate(
        db,
        company,
        identifier,
        body.revision,
        "EDIT",
        body.model_dump(mode="json", exclude_unset=True, exclude={"revision"}),
    )


@router.post("/documents/{identifier}/confirm")
async def confirm(
    identifier: str, body: ActionInput, company: str = Depends(company_id), db=Depends(get_db)
):
    return await mutate(db, company, identifier, body.revision, "CONFIRM", {"status": "CONFIRMED"})


@router.post("/documents/{identifier}/resolve")
async def resolve(
    identifier: str, body: ActionInput, company: str = Depends(company_id), db=Depends(get_db)
):
    if not body.note or not body.note.strip():
        raise HTTPException(422, "Indica el motivo de la revisión")
    return await mutate(
        db, company, identifier, body.revision, "RESOLVE", {"review_note": body.note}
    )


@router.post("/documents/{identifier}/cancel")
async def cancel(
    identifier: str, body: ActionInput, company: str = Depends(company_id), db=Depends(get_db)
):
    return await mutate(db, company, identifier, body.revision, "CANCEL", {"status": "CANCELLED"})


@router.post("/documents/{identifier}/move-period")
async def move_period(
    identifier: str, body: MovePeriodInput, company: str = Depends(company_id), db=Depends(get_db)
):
    return await mutate(
        db,
        company,
        identifier,
        body.revision,
        "MOVE_PERIOD",
        {
            "accounting_period": body.accounting_period,
            "accounting_year": int(body.accounting_period[:4]),
            "accounting_month": int(body.accounting_period[4:]),
            "period_source": "MANUAL",
            "period_validation": "MANUALLY_CONFIRMED",
            "review_note": body.note,
        },
    )


@router.post("/documents/{identifier}/reprocess")
async def reprocess(
    identifier: str, body: ActionInput, company: str = Depends(company_id), db=Depends(get_db)
):
    previous = await require_document(db, company, identifier)
    if not previous.get("storage_key"):
        raise HTTPException(409, "No existe archivo original para reprocesar")
    return await mutate(
        db,
        company,
        identifier,
        body.revision,
        "REPROCESS",
        {
            "status": "QUEUED",
            "ocr": None,
            "attempts": 0,
            "generation": previous.get("generation", 0) + 1,
        },
    )


@router.get("/periods")
async def periods(company: str = Depends(company_id), db=Depends(get_db)):
    return (
        await repo.collection(db, "documents")
        .aggregate(
            [
                {"$match": {"company_id": company}},
                {"$group": {"_id": "$accounting_period", "count": {"$sum": 1}}},
                {"$sort": {"_id": -1}},
            ]
        )
        .to_list(None)
    )


@router.get("/periods/{year}/{month}/documents")
async def period_documents(
    year: int,
    month: int,
    company: str = Depends(company_id),
    db=Depends(get_db),
    page: int = Query(1, ge=1),
):
    period = parse_period(f"{year:04d}{month:02d}")
    if not period:
        raise HTTPException(422, "Periodo inválido")
    query = {"company_id": company, "accounting_period": period}
    rows = (
        await repo.collection(db, "documents")
        .find(query)
        .sort("document_date", -1)
        .skip((page - 1) * 25)
        .limit(25)
        .to_list(25)
    )
    return {
        "items": [repo.public(row) for row in rows],
        "total": await repo.collection(db, "documents").count_documents(query),
    }


@router.get("/periods/{year}/{month}/summary")
async def period_summary(
    year: int, month: int, company: str = Depends(company_id), db=Depends(get_db)
):
    period = parse_period(f"{year:04d}{month:02d}")
    if not period:
        raise HTTPException(422, "Periodo inválido")
    return (
        await repo.collection(db, "documents")
        .aggregate(
            [
                {"$match": {"company_id": company, "accounting_period": period}},
                {
                    "$group": {
                        "_id": {"type": "$document_type", "status": "$status"},
                        "count": {"$sum": 1},
                    }
                },
            ]
        )
        .to_list(None)
    )


@router.post("/batches", status_code=201)
async def create_batch(body: PeriodInput, company: str = Depends(company_id), db=Depends(get_db)):
    batch = {
        "_id": uuid4().hex,
        "company_id": company,
        **body.model_dump(),
        "status": "RECEIVING",
        "received_count": 0,
        "created_at": repo.now(),
        "period_year": int(body.accounting_period[:4]),
        "period_month": int(body.accounting_period[4:]),
    }
    await repo.collection(db, "batches").insert_one(batch)
    return repo.public(batch)


@router.get("/batches")
async def batches(
    company: str = Depends(company_id), db=Depends(get_db), page: int = Query(1, ge=1)
):
    rows = (
        await repo.collection(db, "batches")
        .find({"company_id": company})
        .sort("created_at", -1)
        .skip((page - 1) * 25)
        .limit(25)
        .to_list(25)
    )
    return [repo.public(row) for row in rows]


@router.get("/batches/{identifier}")
async def batch_detail(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    batch = await repo.get(db, "batches", company, identifier)
    if not batch:
        raise HTTPException(404, "Lote no encontrado")
    return {**repo.public(batch), "counts": await repo.batch_counts(db, company, identifier)}


@router.get("/batches/{identifier}/documents")
async def batch_documents(
    identifier: str,
    company: str = Depends(company_id),
    db=Depends(get_db),
    page: int = Query(1, ge=1),
):
    if not await repo.get(db, "batches", company, identifier):
        raise HTTPException(404, "Lote no encontrado")
    rows = (
        await repo.collection(db, "documents")
        .find({"company_id": company, "batch_id": identifier})
        .skip((page - 1) * 25)
        .limit(25)
        .to_list(25)
    )
    return [repo.public(row) for row in rows]


@router.post("/batches/{identifier}/close")
async def close_batch(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    result = await repo.collection(db, "batches").update_one(
        {"_id": identifier, "company_id": company, "status": "RECEIVING"},
        {"$set": {"status": "PROCESSING", "closed_at": repo.now()}},
    )
    if not result.modified_count:
        raise HTTPException(409, "Lote inexistente o ya cerrado")
    return {"status": "PROCESSING"}


@router.post("/batches/{identifier}/confirm")
async def confirm_batch(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    from app.services.captura.conversation import Conversation

    async def apply(tx):
        batch = await repo.get(db, "batches", company, identifier, tx)
        if not batch:
            raise HTTPException(404, "Lote no encontrado")
        handler = Conversation(db, {"_id": company}, {"batch_id": identifier}, tx)
        return await handler.confirm()

    return {"message": await repo.transaction(db, apply)}


@router.post("/reconciliation/run")
async def reconcile(body: PeriodInput, company: str = Depends(company_id), db=Depends(get_db)):
    query = {
        "company_id": company,
        "accounting_period": body.accounting_period,
        "status": {"$in": ["READY", "NEEDS_REVIEW", "CONFIRMED"]},
    }
    count = await repo.collection(db, "documents").count_documents(query)
    if count > 1000:
        raise HTTPException(
            422, "La conciliación interactiva admite hasta 1000 documentos por periodo"
        )
    rows = await repo.collection(db, "documents").find(query).to_list(1000)
    matches = []
    taxes = [row for row in rows if row.get("family") == "TAX"]
    payments = [row for row in rows if row.get("family") == "PAYMENT"]
    for document in taxes:
        for payment in payments:
            score = match_score(document, payment)
            if score >= 85:
                match = {
                    "_id": document["_id"] + ":" + payment["_id"],
                    "company_id": company,
                    "documents": [document["_id"], payment["_id"]],
                    "score": score,
                    "status": "SUGGESTED",
                    "accounting_period": body.accounting_period,
                }
                matches.append(match)

    async def apply(tx):
        await repo.collection(db, "matches").delete_many(
            {
                "company_id": company,
                "accounting_period": body.accounting_period,
                "status": "SUGGESTED",
            },
            session=tx,
        )
        for match in matches:
            await repo.collection(db, "matches").update_one(
                {"_id": match["_id"]}, {"$setOnInsert": match}, upsert=True, session=tx
            )

    await repo.transaction(db, apply)
    return {"suggested": len(matches)}


@router.get("/export")
async def export(period: str, company: str = Depends(company_id), db=Depends(get_db)):
    query = {"company_id": company, "accounting_period": period, "status": "CONFIRMED"}
    count = await repo.collection(db, "documents").count_documents(query)
    if count > 10000:
        raise HTTPException(422, "La exportación interactiva admite hasta 10000 documentos")
    rows = await repo.collection(db, "documents").find(query).to_list(10000)
    return Response(
        "\ufeff" + ExportService.csv(rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="inventario.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/reconciliation/{identifier}/confirm")
async def confirm_match(identifier: str, company: str = Depends(company_id), db=Depends(get_db)):
    async def apply(tx):
        match = await repo.get(db, "matches", company, identifier, tx)
        if not match:
            raise HTTPException(404, "Coincidencia no encontrada")
        tax = await require_document(db, company, match["documents"][0], tx)
        payment = await require_document(db, company, match["documents"][1], tx)
        if match_score(tax, payment) < 85 or any(
            doc["status"] not in {"READY", "CONFIRMED"} for doc in (tax, payment)
        ):
            raise HTTPException(409, "Revisa ambos documentos antes de vincularlos")
        if tax.get("associated_payment") or payment.get("tax_document_id"):
            raise HTTPException(409, "Uno de los documentos ya está vinculado")
        fields = payment["extracted"]["fields"]
        link = {
            "document_id": payment["_id"],
            **{
                name: fields.get("payment." + name, {}).get("value")
                for name in ("method", "channel", "operation_number")
            },
        }
        await repo.collection(db, "documents").update_one(
            {"_id": tax["_id"], "company_id": company},
            {"$set": {"associated_payment": link}, "$inc": {"revision": 1}},
            session=tx,
        )
        await repo.collection(db, "documents").update_one(
            {"_id": payment["_id"], "company_id": company},
            {"$set": {"tax_document_id": tax["_id"]}, "$inc": {"revision": 1}},
            session=tx,
        )
        await repo.collection(db, "matches").update_one(
            {"_id": identifier, "company_id": company},
            {"$set": {"status": "CONFIRMED", "confirmed_at": repo.now()}},
            session=tx,
        )
        for document in (tax, payment):
            await repo.audit(
                db,
                company,
                document["_id"],
                "EMPRESA:" + company,
                "LINK_PAYMENT",
                new=match["documents"],
                session=tx,
            )
        return {"status": "CONFIRMED"}

    return await repo.transaction(db, apply)
