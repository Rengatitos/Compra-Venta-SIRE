import asyncio
from datetime import date

from app.core.captura_config import captura_settings
from app.domain.captura.extraction import extract
from app.domain.captura.models import TERMINAL_STATUSES, OCRResult
from app.domain.captura.period import decide_period
from app.domain.captura.validation import fingerprint, validate
from app.repositories import captura as repo
from app.services.captura.logging import log_event
from app.services.captura.metadata import extract_file_metadata
from app.services.captura.ocr import recognize
from app.services.captura.storage import inspect_file, storage
from app.services.captura.twilio import download_media, send_message


class RetriesExhausted(ValueError):
    """El proceso fue interrumpido repetidamente antes de poder guardar el resultado."""


def summary(document: dict) -> str:
    fields = document.get("extracted", {}).get("fields", {})

    def value(key: str) -> str:
        return str(fields.get(key, {}).get("value") or "No identificado")

    return (
        f"📄 {document.get('document_type', 'UNKNOWN')}\n"
        f"Fecha: {document.get('document_date') or 'No identificada'}\n"
        f"Periodo: {document.get('accounting_period') or 'Pendiente'}\n"
        f"Documento: {value('document.series')}-{value('document.number')}\n"
        f"RUC: {value('issuer.ruc')}\nTotal: {value('amounts.total')}\n"
        f"Estado: {document['status']}\nCONFIRMAR / CORREGIR / CANCELAR"
    )


async def process_document(db, identifier: str) -> None:
    document = await repo.claim(db, "documents", identifier)
    if not document:
        return
    log_event(
        "processing",
        document_id=identifier,
        company_id=document["company_id"],
        batch_id=document.get("batch_id"),
        message_sid=document.get("twilio_message_sid"),
    )
    settings = captura_settings()
    ownership = {"_id": identifier, "lease_id": document["lease_id"], "status": "OCR_PROCESSING"}
    try:
        if document['attempts'] > 3:
            raise RetriesExhausted
        provider = storage(settings)
        if document.get("storage_key"):
            content = await asyncio.to_thread(provider.read, document["storage_key"])
            info = await asyncio.to_thread(inspect_file, content, settings)
        else:
            content = await download_media(document["media_url"], settings)
            info = await asyncio.to_thread(inspect_file, content, settings)
            key = await asyncio.to_thread(provider.put, content)
            document.update(storage_key=key, mime=info["mime"], file_hash=info["sha256"])
            stored = await repo.collection(db, "documents").update_one(
                ownership,
                {
                    "$set": {
                        "storage_key": key,
                        "mime": info["mime"],
                        "file_hash": info["sha256"],
                        "file_size": len(content),
                    }
                },
            )
            if not stored.modified_count:
                await asyncio.to_thread(provider.delete, key)
                return
        if document.get("ocr"):
            ocr = OCRResult.model_validate(document["ocr"])
        else:
            # Reutilizar OCR del mismo archivo dentro de la empresa.
            cached = await repo.collection(db, "documents").find_one(
                {
                    "company_id": document["company_id"],
                    "file_hash": info["sha256"],
                    "ocr": {"$type": "object"},
                    "_id": {"$ne": identifier},
                }
            )
            if document.get('generation', 0) > 0:
                cached = None  # Reproceso explícito: no reutilizar la inferencia anterior.
            ocr = (
                OCRResult.model_validate(cached["ocr"])
                if cached
                else await asyncio.to_thread(recognize, content, info["mime"])
            )
            saved_ocr = await repo.collection(db, "documents").update_one(
                ownership,
                {
                    "$set": {
                        "ocr": ocr.model_dump(),
                        "ocr_confidence": ocr.confidence,
                    }
                },
            )
            if not saved_ocr.modified_count:
                return
        metadata = await asyncio.to_thread(extract_file_metadata, content, info["mime"])
        extracted = extract(ocr)
        field = extracted.fields["document.issue_date"]
        metadata_date = (
            metadata["original_date"]
            or metadata["creation_date"]
            or metadata.get("modification_date")
        )
        decision = decide_period(
            date.fromisoformat(field.value) if field.value else None,
            field.confidence,
            date.fromisoformat(metadata_date) if metadata_date else None,
            document.get("target_period"),
        )
        checks = validate(extracted)
        duplicate_query = [{"file_hash": info["sha256"]}]
        identity = fingerprint(extracted)
        if identity:
            duplicate_query.append({"fingerprint": identity})
        duplicate = await repo.collection(db, "documents").find_one(
            {
                "company_id": document["company_id"],
                "_id": {"$ne": identifier},
                "$or": duplicate_query,
            }
        )
        issues = decision.issues + (
            [f"VALIDATION:{check['rule']}" for check in checks if check["status"] != "PASS"]
        )
        if duplicate:
            issues.append("POSSIBLE_DUPLICATE")
        period = decision.accounting_period
        changes = {
            **decision.model_dump(mode="json"),
            "extracted": extracted.model_dump(mode="json"),
            "family": extracted.classification.family,
            "document_type": extracted.classification.type,
            "sunat_code": extracted.classification.sunat_code,
            "metadata": metadata,
            "fingerprint": identity,
            "validations": checks,
            "issues": issues,
            "possible_duplicate": bool(duplicate),
            "duplicate_of": duplicate["_id"] if duplicate else None,
            "accounting_year": int(period[:4]) if period else None,
            "accounting_month": int(period[4:]) if period else None,
            "status": "NEEDS_REVIEW" if issues else "READY",
            "updated_at": repo.now(),
            "search_text": " ".join(
                str(field.value) for field in extracted.fields.values() if field.value is not None
            ),
        }

        async def finish(tx):
            current = await repo.collection(db, 'documents').find_one(ownership, session=tx)
            if current is None:
                return
            owner = await repo.sync_identity(db, document['company_id'], identifier,
                                             current.get('fingerprint'), identity, tx)
            if owner:
                changes.update(possible_duplicate=True, duplicate_of=owner, status='NEEDS_REVIEW')
                changes['issues'] = list(set([*changes['issues'], 'POSSIBLE_DUPLICATE']))
            updated = await repo.collection(db, "documents").update_one(
                ownership,
                {
                    "$set": changes,
                    "$unset": {"lease_until": "", "lease_id": "", "media_url": ""},
                    "$inc": {"revision": 1},
                },
                session=tx,
            )
            if not updated.modified_count:
                return
            await repo.audit(
                db,
                document["company_id"],
                identifier,
                "WORKER",
                "PROCESSED",
                new={"status": changes["status"]},
                session=tx,
            )
            if not document.get("batch_id") and document.get("phone"):
                await repo.notify(
                    db,
                    f"document:{identifier}:{document.get('generation', 0)}",
                    document["company_id"],
                    document["phone"],
                    summary({**document, **changes}),
                    tx,
                )

        await repo.transaction(db, finish)
        log_event(
            "processed",
            document_id=identifier,
            company_id=document["company_id"],
            status=changes["status"],
        )
    except Exception as error:
        # No persistir str(error): los clientes HTTP pueden incluir URLs y credenciales.
        final = document["attempts"] >= 3 or isinstance(error, ValueError)
        failed = await repo.collection(db, "documents").update_one(
            ownership,
            {
                "$set": {
                    "status": "FAILED" if final else "QUEUED",
                    "error_code": type(error).__name__,
                    "updated_at": repo.now(),
                },
                "$unset": {"lease_until": "", "lease_id": ""},
            },
        )
        if failed.modified_count and final and document.get("phone") and not document.get("batch_id"):
            await repo.notify(
                db,
                f"failed:{identifier}:{document.get('generation', 0)}",
                document["company_id"],
                document["phone"],
                "No pudimos procesar el archivo. Revisa el inventario o envía otra imagen.",
            )


async def finish_batches(db) -> None:
    batches = (
        await repo.collection(db, "batches").find({"status": "PROCESSING"}).limit(100).to_list(100)
    )
    for batch in batches:
        async def finish(tx, batch=batch):
            counts = await repo.batch_counts(db, batch['company_id'], batch['_id'], tx)
            if any(key not in TERMINAL_STATUSES for key in counts):
                return
            result = await repo.collection(db, "batches").update_one(
                {"_id": batch["_id"], "status": "PROCESSING"},
                {"$set": {"status": "READY_FOR_REVIEW", "completed_at": repo.now()}},
                session=tx,
            )
            if result.modified_count and batch.get("phone"):
                body = (
                    f"✅ Lote #{batch['_id'][:8]} procesado\n"
                    f"Periodo: {batch['accounting_period']}\n"
                    f"Documentos: {sum(counts.values())}\nCorrectos: {counts.get('READY', 0)}\n"
                    f"Observados: {counts.get('NEEDS_REVIEW', 0)}\n"
                    f"Errores: {counts.get('FAILED', 0)}\n"
                    f"CONFIRMAR VALIDOS\n{captura_settings().FRONTEND_URL}/lotes/{batch['_id']}"
                )
                await repo.notify(
                    db, "batch:" + batch["_id"], batch["company_id"], batch["phone"], body, tx
                )
                await repo.collection(db, "sessions").update_many(
                    {"company_id": batch["company_id"], "batch_id": batch["_id"]},
                    {"$set": {"state": "BATCH_REVIEW"}},
                    session=tx,
                )

        await repo.transaction(db, finish)


async def deliver_notification(db, identifier: str) -> None:
    message = await repo.claim(db, "notifications", identifier)
    if not message:
        return
    query = {"_id": identifier, "lease_id": message["lease_id"]}
    parts = identifier.split(':')
    current = None
    if parts[0] in {'document', 'failed'} and len(parts) >= 2:
        current = await repo.get(db, 'documents', message['company_id'], parts[1])
        expected = {'FAILED'} if parts[0] == 'failed' else {'READY', 'NEEDS_REVIEW'}
        if current and current.get('status') not in expected:
            current = None
        if current and len(parts) > 2 and str(current.get('generation', 0)) != parts[2]:
            current = None
    elif parts[0] == 'batch' and len(parts) == 2:
        current = await repo.get(db, 'batches', message['company_id'], parts[1])
        if current and current.get('status') != 'READY_FOR_REVIEW':
            current = None
    if current is None:
        await repo.collection(db, 'notifications').update_one(query, {'$set': {'status': 'CANCELLED'}})
        return
    if parts[0] == 'document':
        message['body'] = summary(current)
    phone = await repo.collection(db, "phones").find_one(
        {
            "company_id": message["company_id"],
            "phone": message["phone"],
            "active": True,
        }
    )
    if not phone:
        await repo.collection(db, "notifications").update_one(
            query, {"$set": {"status": "CANCELLED"}}
        )
        return
    try:
        sid = await send_message(
            message["phone"], message["body"], captura_settings(), identifier.split(":", 1)[0]
        )
        await repo.collection(db, "notifications").update_one(
            query,
            {
                "$set": {
                    "status": "SENT",
                    "twilio_sid": sid,
                    "sent_at": repo.now(),
                }
            },
        )
    except Exception as error:
        await repo.collection(db, "notifications").update_one(
            query,
            {
                "$set": {
                    "status": "FAILED" if message["attempts"] >= 3 else "QUEUED",
                    "error_code": type(error).__name__,
                },
                "$unset": {"lease_until": "", "lease_id": ""},
            },
        )
