import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from app.domain.captura.classification import NAMES, RULES
from app.domain.captura.models import TERMINAL_STATUSES, ExtractedDocument, ExtractedField
from app.domain.captura.validation import fingerprint, validate
from app.repositories import captura as repo
from app.services.captura.privacy import SensitiveDataMasker


async def require_document(db, company: str, identifier: str, tx=None) -> dict:
    document = await repo.get(db, "documents", company, identifier, tx)
    if not document:
        raise HTTPException(404, "Documento no encontrado")
    return document


async def mutate(
    db, company: str, identifier: str, revision: int, action: str, changes: dict
) -> dict:
    async def apply(tx):
        previous = await require_document(db, company, identifier, tx)
        if previous["revision"] != revision:
            raise HTTPException(409, "El documento cambió. Actualiza la pantalla.")
        if previous["status"] not in TERMINAL_STATUSES and action != "CANCEL":
            raise HTTPException(409, "Espera a que termine el procesamiento")
        if previous["status"] in {"CONFIRMED", "EXPORTED"}:
            raise HTTPException(409, "Un documento confirmado o exportado no se puede modificar")
        if action in {"EDIT", "MOVE_PERIOD", "RESOLVE"} and previous["status"] not in {
            "READY",
            "NEEDS_REVIEW",
        }:
            raise HTTPException(409, "Reprocesa el documento antes de revisarlo")
        if (
            previous.get("associated_payment") or previous.get("tax_document_id")
        ) and action != "CONFIRM":
            raise HTTPException(409, "Un documento conciliado no se puede modificar")
        if action == "CONFIRM" and previous["status"] != "READY":
            raise HTTPException(409, "Resuelve las observaciones antes de confirmar")
        actual = dict(changes)
        if action == "EDIT":
            actual = edit_changes(previous, changes)
            duplicate_id = await repo.sync_identity(
                db, company, identifier, previous.get("fingerprint"), actual["fingerprint"], tx
            )
            if not duplicate_id and previous.get("file_hash"):
                duplicate = await repo.collection(db, "documents").find_one(
                    {
                        "company_id": company,
                        "_id": {"$ne": identifier},
                        "file_hash": previous["file_hash"],
                    },
                    session=tx,
                )
                duplicate_id = duplicate["_id"] if duplicate else None
            issues = [issue for issue in actual["issues"] if issue != "POSSIBLE_DUPLICATE"]
            if duplicate_id:
                issues.append("POSSIBLE_DUPLICATE")
            actual.update(
                possible_duplicate=bool(duplicate_id),
                duplicate_of=duplicate_id,
                issues=issues,
                status="NEEDS_REVIEW" if issues else "READY",
            )
        if action == "MOVE_PERIOD":
            remaining = [
                issue
                for issue in previous.get("issues", [])
                if issue
                not in {
                    "DATE_PERIOD_MISMATCH",
                    "PERIOD_REQUIRED",
                    "DATE_UNCERTAIN",
                    "DATE_NOT_FOUND",
                }
            ]
            actual.update(issues=remaining, status="NEEDS_REVIEW" if remaining else "READY")
        if action == "RESOLVE":
            # La revisión humana queda explícita, no sustituye los campos ausentes.
            if not previous.get("accounting_period") or not previous.get("extracted"):
                raise HTTPException(409, "Falta periodo o extracción")
            if any(check["status"] == "FAIL" for check in previous.get("validations", [])):
                raise HTTPException(409, "Corrige las validaciones fallidas antes de resolver")
            if previous.get("period_validation") == "MISMATCH":
                raise HTTPException(409, "Resuelve primero el periodo")
            actual.update(status="READY", issues=[], reviewed_issues=previous.get("issues", []))
        if previous.get("batch_id"):
            batch = await repo.get(db, "batches", company, previous["batch_id"], tx)
            if batch:
                batch_changes = {"$inc": {"revision": 1}}
                if action == "REPROCESS" and batch["status"] not in {"RECEIVING", "CANCELLED"}:
                    batch_changes["$set"] = {"status": "PROCESSING"}
                await repo.collection(db, "batches").update_one(
                    {"_id": batch["_id"], "company_id": company}, batch_changes, session=tx
                )
        actual["updated_at"] = repo.now()
        await repo.collection(db, "documents").update_one(
            {"_id": identifier, "company_id": company, "revision": revision},
            {"$set": actual, "$inc": {"revision": 1}},
            session=tx,
        )
        await repo.audit(
            db,
            company,
            identifier,
            "EMPRESA:" + company,
            action,
            {key: previous.get(key) for key in actual},
            actual,
            tx,
        )
        return {**previous, **actual, "revision": revision + 1}

    return repo.public(await repo.transaction(db, apply))


def edit_changes(previous: dict, changes: dict) -> dict:
    extracted = ExtractedDocument.model_validate(previous.get("extracted", {}))
    for key, value in changes.get("fields", {}).items():
        if key not in extracted.fields:
            raise HTTPException(422, "Campo desconocido")
        if value is not None:
            value = SensitiveDataMasker.cards(value.strip()) or None
        if value and (key.startswith("amounts.") or key.startswith("honorarios.")):
            try:
                number = Decimal(value)
                if not number.is_finite() or abs(number) > Decimal("1000000000000"):
                    raise InvalidOperation
                value = str(number.quantize(Decimal(".01")))
            except InvalidOperation:
                raise HTTPException(422, "Monto inválido") from None
        if value and key == "document.issue_date":
            try:
                date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, "Fecha inválida") from None
        extracted.fields[key] = ExtractedField(
            value=value,
            status="EXTRACTED" if value is not None else "PRESENT_EMPTY",
            confidence=1,
            source="MANUAL",
        )
    kind = changes.get("document_type")
    if kind:
        reverse = {name: code for code, name in NAMES.items()}
        code = reverse.get(kind, kind)
        if code not in RULES and kind not in {"OTHER_DOCUMENT", "UNKNOWN"}:
            raise HTTPException(422, "Tipo de documento inválido")
        extracted.classification.type = NAMES.get(code, code)
        extracted.classification.sunat_code = code if code.isdigit() else None
        extracted.classification.family = "TAX" if code.isdigit() else "PAYMENT"
        if kind in {"OTHER_DOCUMENT", "UNKNOWN"}:
            extracted.classification.family = "OTHER"
    if "document_date" in changes:
        value = changes["document_date"]
        extracted.fields["document.issue_date"] = ExtractedField(
            value=value,
            status="EXTRACTED" if value else "PRESENT_EMPTY",
            source="MANUAL",
            confidence=1,
        )
    checks = validate(extracted)
    issues = [
        item
        for item in previous.get("issues", [])
        if not item.startswith("VALIDATION:") and item != "DATE_PERIOD_MISMATCH"
    ]
    issues += ["VALIDATION:" + check["rule"] for check in checks if check["status"] != "PASS"]
    date_field = extracted.fields["document.issue_date"]
    issue_date = date_field.value if date_field.confidence >= 0.85 else None
    period_validation = previous.get("period_validation", "UNVERIFIED")
    date_edited = "document.issue_date" in changes.get("fields", {}) or "document_date" in changes
    if issue_date and (period_validation != "MANUALLY_CONFIRMED" or date_edited):
        detected = date.fromisoformat(issue_date).strftime("%Y%m")
        if previous.get("accounting_period") != detected:
            issues = list(set([*issues, "DATE_PERIOD_MISMATCH"]))
            period_validation = "MISMATCH"
        else:
            period_validation = "MATCH"
            issues = [item for item in issues if item not in {"DATE_NOT_FOUND", "DATE_UNCERTAIN"}]
    if not issue_date and date_edited:
        issues = list(set([*issues, "DATE_NOT_FOUND"]))
        period_validation = "UNVERIFIED"
    return {
        "extracted": extracted.model_dump(mode="json"),
        "fingerprint": fingerprint(extracted),
        "validations": checks,
        "issues": issues,
        "document_type": extracted.classification.type,
        "family": extracted.classification.family,
        "sunat_code": extracted.classification.sunat_code,
        "document_date": issue_date,
        "period_validation": period_validation,
        "status": "NEEDS_REVIEW" if issues else "READY",
        "search_text": " ".join(
            str(field.value) for field in extracted.fields.values() if field.value is not None
        ),
    }


class ExportService:
    @staticmethod
    def csv(documents: list[dict]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["id", "periodo", "tipo", "fecha", "total", "medio_pago", "numero_operacion"]
        )
        for document in documents:
            fields = document.get("extracted", {}).get("fields", {})
            associated = document.get("associated_payment", {})

            def value(key, fields=fields, associated=associated):
                text = str(
                    fields.get(key, {}).get("value")
                    or associated.get(key.removeprefix("payment."))
                    or ""
                )
                return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text

            writer.writerow(
                [
                    document["_id"],
                    document.get("accounting_period"),
                    document.get("document_type"),
                    document.get("document_date"),
                    value("amounts.total"),
                    value("payment.channel") or value("payment.method"),
                    value("payment.operation_number"),
                ]
            )
        return output.getvalue()
