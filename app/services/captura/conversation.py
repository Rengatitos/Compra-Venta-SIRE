"""Handlers de conversación; se ejecutan dentro de una transacción Mongo."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.core.captura_config import captura_settings
from app.domain.captura.models import SessionState
from app.domain.captura.period import parse_period
from app.repositories import captura as repo

MENU = (
    "1 Registrar comprobante\n2 Registrar lote\n3 Último lote\n"
    "4 Pendientes\n5 Cambiar periodo\n6 Ayuda"
)


class Conversation:
    def __init__(self, db, company: dict, conversation: dict, transaction):
        self.db, self.company, self.session, self.tx = db, company, conversation, transaction
        self.company_id = str(company["_id"])

    async def handle(self, body: str, media: list[dict], sid: str) -> str:
        command = body.strip().upper()
        if media:
            return await self.receive(media, sid)
        commands = {
            "1": self.single,
            "REGISTRAR": self.single,
            "FACTURA": self.single,
            "BOLETA": self.single,
            "COMPROBANTE": self.single,
            "2": self.batch,
            "LOTE": self.batch,
            "MASIVO": self.batch,
            "FIN": self.close,
            "CANCELAR": self.cancel,
            "3": self.last,
            "ESTADO": self.last,
            "ULTIMO LOTE": self.last,
            "4": self.pending,
            "PENDIENTES": self.pending,
            "5": self.period,
            "CAMBIAR PERIODO": self.period,
            "6": self.help,
            "AYUDA": self.help,
            "MENU": self.help,
            "HOLA": self.help,
            "CONFIRMAR": self.confirm,
            "CONFIRMAR VALIDOS": self.confirm,
            "CORREGIR": self.correct,
        }
        # En la selección de periodo 1/2 significan mes actual/anterior.
        if self.session["state"] == SessionState.BATCH_SELECTING_PERIOD and command not in {
            "CANCELAR",
            "AYUDA",
            "MENU",
        }:
            return await self.select_period(command)
        handler = commands.get(command, self.help)
        return await handler()

    async def help(self) -> str:
        return f"Hola 👋\nRUC: {self.company['ruc']}\n{MENU}"

    async def single(self) -> str:
        if self.session.get("batch_id"):
            return "Tienes un lote activo. Escribe FIN o CANCELAR antes de iniciar otro registro."
        self.session["state"] = SessionState.WAITING_SINGLE_DOCUMENT
        return "Envía una fotografía o un PDF del comprobante."

    async def batch(self) -> str:
        if self.session.get("batch_id"):
            return "Ya tienes un lote activo. Envía documentos o escribe FIN."
        self.session.update(state=SessionState.BATCH_SELECTING_PERIOD, selecting_batch=True)
        return "¿Qué periodo registrarás?\n1 Mes actual\n2 Mes anterior\nO escribe SEPTIEMBRE 2026."

    async def period(self) -> str:
        if self.session.get("batch_id"):
            return "El periodo del lote ya está fijado. Revisa las excepciones en el inventario."
        self.session.update(state=SessionState.BATCH_SELECTING_PERIOD, selecting_batch=False)
        return "Escribe el periodo, por ejemplo SEPTIEMBRE 2026."

    async def select_period(self, text: str) -> str:
        period = parse_period(text, datetime.now(ZoneInfo("America/Lima")).date())
        if not period:
            return "Periodo no reconocido. Escribe SEPTIEMBRE 2026 o 202609."
        self.session["selected_period"] = period
        if not self.session.get("selecting_batch"):
            identifier = self.session.get("document_id")
            document = await repo.get(self.db, "documents", self.company_id, identifier, self.tx)
            if document and document["status"] in {"READY", "NEEDS_REVIEW"}:
                issues = [
                    issue
                    for issue in document.get("issues", [])
                    if issue
                    not in {
                        "DATE_PERIOD_MISMATCH",
                        "PERIOD_REQUIRED",
                        "DATE_UNCERTAIN",
                        "DATE_NOT_FOUND",
                    }
                ]
                await repo.collection(self.db, "documents").update_one(
                    {"_id": identifier, "company_id": self.company_id},
                    {
                        "$set": {
                            "accounting_period": period,
                            "accounting_year": int(period[:4]),
                            "accounting_month": int(period[4:]),
                            "period_source": "MANUAL",
                            "period_validation": "MANUALLY_CONFIRMED",
                            "issues": issues,
                            "status": "NEEDS_REVIEW" if issues else "READY",
                        },
                        "$inc": {"revision": 1},
                    },
                    session=self.tx,
                )
                await repo.audit(
                    self.db,
                    self.company_id,
                    identifier,
                    "WHATSAPP",
                    "MOVE_PERIOD",
                    document.get("accounting_period"),
                    period,
                    self.tx,
                )
                self.session["state"] = SessionState.WAITING_SINGLE_CONFIRMATION
                return f"Periodo asignado: {period}. Escribe CONFIRMAR o CORREGIR."
            self.session["state"] = SessionState.IDLE
            return f"Periodo de referencia: {period}. La fecha OCR se comprobará contra él."
        batch_id = uuid4().hex
        await repo.collection(self.db, "batches").insert_one(
            {
                "_id": batch_id,
                "company_id": self.company_id,
                "accounting_period": period,
                "period_year": int(period[:4]),
                "period_month": int(period[4:]),
                "status": "RECEIVING",
                "received_count": 0,
                "created_at": repo.now(),
                "phone": self.session["phone"],
            },
            session=self.tx,
        )
        self.session.update(batch_id=batch_id, state=SessionState.BATCH_RECEIVING)
        return (
            f"📚 Lote #{batch_id[:8]} — {period}\nEnvía tus comprobantes. Escribe FIN al terminar."
        )

    async def receive(self, media: list[dict], sid: str) -> str:
        batch_id = self.session.get("batch_id")
        if batch_id and self.session["state"] != SessionState.BATCH_RECEIVING:
            return "El lote está cerrado. Confirma o cancela la revisión antes de iniciar otro."
        if not batch_id and len(media) > 1:
            return "Para varios archivos escribe LOTE y selecciona el periodo primero."
        if self.session["state"] == SessionState.BATCH_SELECTING_PERIOD:
            return "Selecciona primero el periodo del lote."
        if not batch_id and self.session.get("document_id"):
            previous = await repo.get(
                self.db, "documents", self.company_id, self.session["document_id"], self.tx
            )
            if previous and previous["status"] not in {"CONFIRMED", "CANCELLED", "FAILED"}:
                return "Hay un comprobante pendiente. Escribe CONFIRMAR, CORREGIR o CANCELAR."
        if batch_id:
            batch = await repo.get(self.db, "batches", self.company_id, batch_id, self.tx)
            if batch["received_count"] + len(media) > captura_settings().MAX_BATCH_DOCUMENTS:
                return "Alcanzaste el límite del lote. Escribe FIN."
            await repo.collection(self.db, "batches").update_one(
                {"_id": batch_id}, {"$inc": {"received_count": len(media)}}, session=self.tx
            )
        for index, item in enumerate(media):
            document = repo.new_document(
                self.company_id,
                "WHATSAPP",
                batch_id=batch_id,
                phone=self.session["phone"],
                twilio_message_sid=sid,
                media_index=index,
                **item,
                target_period=self.session.get("selected_period"),
                twilio_received_at=None,
                received_at_source="WEBHOOK",
            )
            await repo.collection(self.db, "documents").insert_one(document, session=self.tx)
            self.session["document_id"] = document["_id"]
        if batch_id:
            return (
                f"📄 Documento recibido. Lote #{batch_id[:8]}. "
                f"Recibidos: {batch['received_count'] + len(media)}."
            )
        self.session["state"] = SessionState.WAITING_SINGLE_CONFIRMATION
        return "📄 Comprobante recibido. Estoy procesándolo…"

    async def close(self) -> str:
        batch_id = self.session.get("batch_id")
        if not batch_id:
            return "No tienes un lote abierto. Escribe LOTE para crear uno."
        await repo.collection(self.db, "batches").update_one(
            {"_id": batch_id, "company_id": self.company_id, "status": "RECEIVING"},
            {"$set": {"status": "PROCESSING", "closed_at": repo.now()}},
            session=self.tx,
        )
        self.session["state"] = SessionState.BATCH_PROCESSING
        counts = await repo.batch_counts(self.db, self.company_id, batch_id, self.tx)
        return f"📚 Lote cerrado. Recibidos: {sum(counts.values())}. Terminaremos en segundo plano."

    async def last(self) -> str:
        batch = await repo.collection(self.db, "batches").find_one(
            {"company_id": self.company_id}, sort=[("created_at", -1)], session=self.tx
        )
        if not batch:
            return "Todavía no tienes lotes."
        counts = await repo.batch_counts(self.db, self.company_id, batch["_id"], self.tx)
        return (
            f"Lote #{batch['_id'][:8]} — {batch['accounting_period']}\n"
            f"{batch['status']}\nDocumentos: {sum(counts.values())}"
        )

    async def pending(self) -> str:
        count = await repo.collection(self.db, "documents").count_documents(
            {"company_id": self.company_id, "status": {"$in": ["NEEDS_REVIEW", "FAILED"]}},
            session=self.tx,
        )
        url = captura_settings().FRONTEND_URL
        return f"⚠️ Pendientes: {count}.\n{url}/comprobantes?observados=true"

    async def correct(self) -> str:
        self.session["state"] = SessionState.WAITING_CORRECTION
        identifier = self.session.get("document_id", "")
        return (
            f"Revisa y corrige aquí:\n{captura_settings().FRONTEND_URL}/comprobantes/{identifier}"
        )

    async def confirm(self) -> str:
        batch_id = self.session.get("batch_id")
        if batch_id:
            batch = await repo.get(self.db, "batches", self.company_id, batch_id, self.tx)
            if not batch or batch["status"] not in {"READY_FOR_REVIEW", "PARTIALLY_CONFIRMED"}:
                return "El lote aún no terminó. Escribe FIN y espera el resumen."
            query = {"company_id": self.company_id, "batch_id": batch_id, "status": "READY"}
        else:
            query = {
                "company_id": self.company_id,
                "_id": self.session.get("document_id"),
                "status": "READY",
            }
        documents = (
            await repo.collection(self.db, "documents").find(query, session=self.tx).to_list(None)
        )
        for document in documents:
            await repo.collection(self.db, "documents").update_one(
                {"_id": document["_id"]},
                {
                    "$set": {"status": "CONFIRMED", "updated_at": repo.now()},
                    "$inc": {"revision": 1},
                },
                session=self.tx,
            )
            await repo.audit(
                self.db,
                self.company_id,
                document["_id"],
                "WHATSAPP",
                "CONFIRM",
                old=document["status"],
                new="CONFIRMED",
                session=self.tx,
            )
        if batch_id:
            counts = await repo.batch_counts(self.db, self.company_id, batch_id, self.tx)
            pending = sum(v for k, v in counts.items() if k not in {"CONFIRMED", "CANCELLED"})
            await repo.collection(self.db, "batches").update_one(
                {"_id": batch_id},
                {"$set": {"status": "PARTIALLY_CONFIRMED" if pending else "CONFIRMED"}},
                session=self.tx,
            )
        elif not documents:
            return "Aún no está listo o tiene observaciones. Escribe CORREGIR para revisarlo."
        self.session.update(
            state=SessionState.IDLE, batch_id=None, document_id=None, selected_period=None
        )
        return f"✅ Confirmados: {len(documents)}. Los observados quedan en el inventario."

    async def cancel(self) -> str:
        batch_id = self.session.get("batch_id")
        if batch_id:
            await repo.collection(self.db, "batches").update_one(
                {"_id": batch_id, "company_id": self.company_id},
                {"$set": {"status": "CANCELLED"}},
                session=self.tx,
            )
        query = {
            "company_id": self.company_id,
            **({"batch_id": batch_id} if batch_id else {"_id": self.session.get("document_id")}),
            "status": {"$nin": ["CONFIRMED", "EXPORTED"]},
        }
        await repo.collection(self.db, "documents").update_many(
            query, {"$set": {"status": "CANCELLED"}, "$inc": {"revision": 1}}, session=self.tx
        )
        await repo.audit(
            self.db,
            self.company_id,
            batch_id or self.session.get("document_id", ""),
            "WHATSAPP",
            "CANCEL",
            session=self.tx,
        )
        self.session.update(
            state=SessionState.IDLE, batch_id=None, document_id=None, selected_period=None
        )
        return "Registro cancelado. Los archivos se conservan para trazabilidad."
