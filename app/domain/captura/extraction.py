"""Extractores conservadores: un valor necesita evidencia literal en el OCR."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.domain.captura.classification import classify, normalize
from app.domain.captura.layout import lines
from app.domain.captura.models import (
    ExtractedDocument,
    ExtractedField,
    FieldStatus,
    OCRBlock,
    OCRResult,
)

GROUPS = {
    "issuer": "document_type document_number ruc name address",
    "customer": "document_type document_number name address",
    "document": "series number issue_date issue_time currency",
    "amounts": "taxable exempt unaffected subtotal discount igv other_taxes total",
    "payment": (
        "method channel destination_channel operation_number authorization_number "
        "reference card_brand card_last4 recipient bank phone processor merchant terminal "
        "transaction_status contactless"
    ),
    "service": "provider type customer_code holder billing_period description due_date consumption",
    "vehicle": "plate odometer",
    "references": "document_type series number reason",
    "transport": "date origin destination carrier carrier_ruc license weight packages",
    "honorarios": "gross retention net",
}
LABELS = {
    "issuer.ruc": r"(?:RUC(?: EMISOR)?|R\.U\.C\.)",
    "issuer.name": r"(?:RAZON SOCIAL|EMISOR|PROVEEDOR)",
    "issuer.address": r"(?:DIRECCION EMISOR|DOMICILIO FISCAL)",
    "customer.name": r"(?:CLIENTE|SENOR\(ES\)|SENORES)",
    "customer.document_number": r"(?:RUC CLIENTE|DNI(?: CLIENTE)?|DOCUMENTO CLIENTE)",
    "customer.address": r"DIRECCION CLIENTE",
    "document.issue_date": (
        r"(?:FECHA(?: DE)? EMISION|"
        r"FECHA(?!\s+(?:DE\s+)?(?:VENCIMIENTO|PAGO|TRASLADO)))"
    ),
    "document.issue_time": r"HORA",
    "document.currency": r"MONEDA",
    "amounts.taxable": r"(?:OP\.? GRAVADA[S]?|OPERACIONES GRAVADAS|BASE IMPONIBLE)",
    "amounts.exempt": r"(?:OP\.? EXONERADA[S]?|EXONERADO)",
    "amounts.unaffected": r"(?:OP\.? INAFECTA[S]?|INAFECTO)",
    "amounts.subtotal": r"(?:SUBTOTAL|SUB TOTAL)",
    "amounts.discount": r"DESCUENTO",
    "amounts.igv": r"(?:I\.?G\.?V\.?)(?:\s*18\s*%)?",
    "amounts.other_taxes": r"OTROS TRIBUTOS",
    "amounts.total": r"(?:IMPORTE TOTAL|TOTAL A PAGAR|TOTAL|MONTO|IMPORTE)",
    "payment.method": r"(?:FORMA DE PAGO|MEDIO DE PAGO)",
    "payment.operation_number": r"(?:N[°ºO.]?\s*(?:DE )?OPERACION|NUMERO DE OPERACION|OPERACION)",
    "payment.authorization_number": r"(?:AUTORIZACION|CODIGO DE AUTORIZACION)",
    "payment.reference": r"REFERENCIA",
    "payment.recipient": r"(?:DESTINATARIO|BENEFICIARIO|PARA)",
    "payment.bank": r"BANCO",
    "payment.phone": r"(?:CELULAR|TELEFONO)",
    "payment.processor": r"PROCESADOR",
    "payment.merchant": r"COMERCIO",
    "payment.terminal": r"TERMINAL",
    "payment.transaction_status": r"ESTADO",
    "service.provider": r"EMPRESA DE SERVICIO",
    "service.customer_code": r"(?:SUMINISTRO|CODIGO CLIENTE)",
    "service.holder": r"TITULAR",
    "service.billing_period": r"PERIODO FACTURADO",
    "service.description": r"(?:CONCEPTO|DESCRIPCION|SERVICIO PRESTADO)",
    "service.due_date": r"(?:VENCIMIENTO|FECHA DE VENCIMIENTO)",
    "service.consumption": r"CONSUMO",
    "vehicle.plate": r"PLACA",
    "vehicle.odometer": r"(?:KILOMETRAJE|ODOMETRO)",
    "references.reason": r"(?:MOTIVO|RAZON DE MODIFICACION)",
    "transport.date": r"FECHA DE TRASLADO",
    "transport.origin": r"PUNTO DE PARTIDA",
    "transport.destination": r"PUNTO DE LLEGADA",
    "transport.carrier": r"TRANSPORTISTA",
    "transport.carrier_ruc": r"RUC TRANSPORTISTA",
    "transport.license": r"LICENCIA",
    "transport.weight": r"PESO",
    "transport.packages": r"BULTOS",
    "honorarios.gross": r"MONTO BRUTO",
    "honorarios.retention": r"RETENCION(?:\s*8\s*%)?",
    "honorarios.net": r"(?:MONTO NETO|NETO RECIBIDO)",
}


def money(value: str) -> str | None:
    value = re.sub(r"^(?:S/\.?|PEN|USD|US\$|\$)\s*", "", value.strip())
    if not re.fullmatch(r"-?[\d.,]+", value):
        return None
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = (
            value.replace(",", ".") if len(value.rsplit(",", 1)[1]) == 2 else value.replace(",", "")
        )
    try:
        return str(Decimal(value).quantize(Decimal(".01")))
    except InvalidOperation:
        return None


def parse_date(value: str) -> date | None:
    match = re.search(r"\b(\d{1,4})[-/.](\d{1,2})[-/.](\d{2,4})\b", value)
    if not match:
        return None
    a, b, c = map(int, match.groups())
    year, month, day = (a, b, c) if len(match[1]) == 4 else (c, b, a)
    if year < 100:
        year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def evidence(block: OCRBlock, value: str | None) -> ExtractedField:
    return ExtractedField(
        value=value,
        status=FieldStatus.EXTRACTED if value else FieldStatus.PRESENT_EMPTY,
        confidence=block.confidence,
        raw_text=block.text,
        page=block.page,
        bbox=block.bbox,
    )


class Extractor(Protocol):
    def extract(self, ocr: OCRResult) -> ExtractedDocument: ...


class LabelExtractor:
    """Los rótulos vacíos no toman el valor del siguiente campo por proximidad."""

    def extract(self, ocr: OCRResult) -> ExtractedDocument:
        ocr = lines(ocr)
        fields = {
            f"{group}.{name}": ExtractedField()
            for group, names in GROUPS.items()
            for name in names.split()
        }
        result = ExtractedDocument(classification=classify(ocr.text), fields=fields)
        fields = result.fields
        for key, label in LABELS.items():
            candidates = []
            for block in ocr.blocks:
                match = re.fullmatch(rf"\s*{label}\s*(?::|\s)\s*(.*?)\s*", normalize(block.text))
                if match:
                    # El índice del texto normalizado conserva los caracteres de origen.
                    raw = block.text[match.start(1) : match.end(1)].strip()
                    field = evidence(block, raw or None)
                    if raw and (key.startswith("amounts.") or key.startswith("honorarios.")):
                        field.value = money(raw)
                    if raw and key.endswith(("issue_date", "due_date")):
                        parsed = parse_date(raw)
                        field.value = parsed.isoformat() if parsed else None
                    if raw and key == "vehicle.plate":
                        plate = re.sub(r"\s+", "", raw.upper())
                        field.value = (
                            plate if re.fullmatch(r"[A-Z0-9]{3}-?[A-Z0-9]{3}", plate) else None
                        )
                    if raw and key == "issuer.ruc":
                        field.value = raw if re.fullmatch(r"\d{11}", raw) else None
                    if raw and field.value is None:
                        field.status = FieldStatus.ILLEGIBLE
                    candidates.append(field)
            if candidates:
                # Varios valores distintos necesitan revisión; no elegir uno arbitrariamente.
                chosen = max(candidates, key=lambda field: field.confidence)
                if len({str(field.value) for field in candidates if field.value}) > 1:
                    chosen = chosen.model_copy(
                        update={"value": None, "status": FieldStatus.ILLEGIBLE}
                    )
                fields[key] = chosen
        self._document_number(ocr, result)
        self._payment(ocr, result)
        self._date(ocr, result)
        self._items(ocr, result)
        for block in ocr.blocks:
            text = normalize(block.text)
            if re.search(r"S/\.?\s*\d", text) and fields["document.currency"].value is None:
                fields["document.currency"] = evidence(block, "PEN")
            elif re.search(r"(?:US\$|USD)\s*\d", text):
                fields["document.currency"] = evidence(block, "USD")
        return result

    def _items(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        table = False
        for block in ocr.blocks:
            text = normalize(block.text)
            if "DESCRIPCION" in text and ("CANT" in text or "CANTIDAD" in text):
                table = True
                continue
            if not table:
                continue
            if re.match(r"(?:SUBTOTAL|SUB TOTAL|TOTAL|IGV|OP\.)\b", text):
                table = False
                continue
            row = re.fullmatch(
                r"(?P<quantity>\d+(?:[.,]\d+)?)\s+(?P<unit>UND|UNIDAD|NIU|KG|LTR|GAL|M3)\s+"
                r"(?P<description>.+?)\s+(?P<unit_price>\d+[.,]\d{2})\s+"
                r"(?P<total>\d+[.,]\d{2})",
                text,
            )
            if row:
                item = {
                    key: ExtractedField()
                    for key in (
                        "code",
                        "description",
                        "quantity",
                        "unit",
                        "unit_price",
                        "discount",
                        "total",
                    )
                }
                for key, value in row.groupdict().items():
                    if key in {"unit_price", "total"}:
                        value = money(value)
                    elif key == "quantity":
                        value = value.replace(",", ".")
                    item[key] = evidence(block, value)
                result.items.append(item)

    def _document_number(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        for block in ocr.blocks:
            text = normalize(block.text)
            match = re.search(r"\b([FEBT][A-Z0-9]{3})\s*-\s*(\d{1,12})\b", text)
            if not match:
                continue
            reference = any(word in text for word in ("AFECTADO", "REFERENCIA", "MODIFICA"))
            prefix = "references" if reference else "document"
            if result.fields[f"{prefix}.series"].value is None:
                result.fields[f"{prefix}.series"] = evidence(block, match[1])
                result.fields[f"{prefix}.number"] = evidence(block, match[2])

    def _payment(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        if result.classification.family != "PAYMENT":
            return
        result.fields["vehicle.plate"] = ExtractedField(status=FieldStatus.NOT_APPLICABLE)
        for block in ocr.blocks:
            text = normalize(block.text)
            for channel in ("YAPE", "PLIN", "VISA", "MASTERCARD"):
                if channel in text:
                    key = (
                        "payment.card_brand"
                        if channel in {"VISA", "MASTERCARD"}
                        else "payment.channel"
                    )
                    result.fields[key] = evidence(block, channel)
            match = re.search(r"(?:\*{2,}|X{2,})\s*(\d{4})\b", text)
            if match:
                result.fields["payment.card_last4"] = evidence(block, match[1])
            if result.fields["amounts.total"].value is None and re.fullmatch(
                r"\s*(?:S/\.?|US\$|USD)\s*[\d.,]+\s*", text
            ):
                result.fields["amounts.total"] = evidence(block, money(text))

    def _date(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        if result.fields["document.issue_date"].status != FieldStatus.NOT_PRESENT:
            return
        candidates = [
            (block, parse_date(block.text))
            for block in ocr.blocks
            if re.fullmatch(r"\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\s*", block.text)
        ]
        valid = [(block, value) for block, value in candidates if value]
        if len({value for _, value in valid}) == 1:
            block, value = valid[0]
            result.fields["document.issue_date"] = evidence(block, value.isoformat())


def extract(ocr: OCRResult) -> ExtractedDocument:
    return LabelExtractor().extract(ocr)
