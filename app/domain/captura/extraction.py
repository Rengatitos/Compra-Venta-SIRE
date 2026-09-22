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
        r"FECHA(?!\s+(?:DE\s+)?(?:VENCIMIENTO|PAGO|TRASLADO|DOCUMENTO|REFERENCIA)))"
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
    value = re.sub(r"^(?:S/\.?|PEN|USD|US\$|EUR|€|\$)\s*", "", value.strip(), flags=re.I)
    if re.fullmatch(r"-?\d+(?:[.,]\d{1,2})?", value):
        value = value.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", value):
        value = value.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", value):
        value = value.replace(".", "").replace(",", ".")
    else:
        return None
    try:
        return str(Decimal(value).quantize(Decimal(".01")))
    except InvalidOperation:
        return None


def parse_date(value: str) -> date | None:
    matches = list(re.finditer(
        r"(?<![\d/.-])(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"\d{1,2}[-/.]\d{1,2}[-/.](?:\d{4}|\d{2}))(?![\d/.-])",
        value,
    ))
    if not matches:
        return None
    dates = set()
    try:
        for match in matches:
            parts = re.split(r"[-/.]", match[0])
            a, b, c = map(int, parts)
            year, month, day = (a, b, c) if len(parts[0]) == 4 else (c, b, a)
            if len(parts[0]) != 4 and len(parts[2]) == 2:
                year += 2000
            dates.add(date(year, month, day))
    except ValueError:
        return None
    return dates.pop() if len(dates) == 1 else None


def raw_group(text: str, match: re.Match, group: str | int) -> str:
    """Devuelve el fragmento original incluso si Unicode cambió su longitud."""
    offsets = [index for index, char in enumerate(text) for _ in normalize(char)]
    start, end = match.span(group)
    if start == end:
        return ""
    return text[offsets[start] : offsets[end] if end < len(offsets) else len(text)].strip()


def choose(candidates: list[ExtractedField]) -> ExtractedField:
    chosen = max(candidates, key=lambda field: field.confidence)
    if len({str(field.value) for field in candidates if field.value is not None}) > 1:
        return chosen.model_copy(update={"value": None, "status": FieldStatus.ILLEGIBLE})
    return chosen


def currency(value: str) -> str | None:
    aliases = {
        "PEN": "PEN", "S/": "PEN", "S/.": "PEN", "SOL": "PEN", "SOLES": "PEN",
        "NUEVOS SOLES": "PEN", "USD": "USD", "US$": "USD", "DOLARES": "USD",
        "DOLARES AMERICANOS": "USD", "EUR": "EUR", "EUROS": "EUR", "€": "EUR",
    }
    return aliases.get(normalize(value).strip())


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
                    raw = raw_group(block.text, match, 1)
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
                    if raw and key == "document.currency":
                        field.value = currency(raw)
                    if raw and field.value is None:
                        field.status = FieldStatus.ILLEGIBLE
                    candidates.append(field)
            if candidates:
                # Varios valores distintos necesitan revisión; no elegir uno arbitrariamente.
                fields[key] = choose(candidates)
        self._document_number(ocr, result)
        self._payment(ocr, result)
        self._date(ocr, result)
        self._items(ocr, result)
        self._currency(ocr, result)
        return result

    def _currency(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        if result.fields["document.currency"].status != FieldStatus.NOT_PRESENT:
            return
        candidates = []
        for block in ocr.blocks:
            for symbol, value in ((r"S/\.?|PEN", "PEN"), (r"US\$|USD", "USD"), (r"EUR|€", "EUR")):
                if re.search(rf"(?<!\w)(?:{symbol})\s*-?\d", normalize(block.text)):
                    candidates.append(evidence(block, value))
        if candidates:
            result.fields["document.currency"] = choose(candidates)

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
                r"(?P<description>.+?)\s+(?P<unit_price>[\d.,]+)\s+"
                r"(?P<total>[\d.,]+)",
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
                    elif key == "description":
                        value = raw_group(block.text, row, key)
                    item[key] = evidence(block, value)
                    if value is None:
                        item[key].status = FieldStatus.ILLEGIBLE
                result.items.append(item)

    def _document_number(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        candidates = {prefix: [] for prefix in ("document", "references")}
        reference = False
        reference_page = None
        is_note = result.classification.sunat_code in {"07", "08", "87", "88", "97", "98"}
        for block in ocr.blocks:
            text = normalize(block.text)
            if reference_page != block.page:
                reference = False
            reference_page = block.page
            if re.search(r"\b(?:AFECTAD[OA]|REFERENCIA|MODIFICAD[OA]|MODIFICA)\b", text):
                reference = True
            elif is_note and re.search(r"\b(?:FACTURA|BOLETA|RECIBO POR HONORARIOS)\b", text):
                reference = True
            elif re.search(r"\bNOTA DE (?:CREDITO|DEBITO)\b", text):
                reference = False
            elif reference and re.match(r"(?:MOTIVO|RAZON|SUBTOTAL|TOTAL|IGV|FECHA)\b", text):
                reference = False
            prefix = "references" if reference else "document"
            if reference:
                for title, code in (("FACTURA", "01"), ("BOLETA", "03"), ("RECIBO POR HONORARIOS", "02")):
                    if re.search(rf"\b{title}\b", text):
                        result.fields["references.document_type"] = evidence(block, code)
            for match in re.finditer(r"\b([FEBT][A-Z0-9]{3})\s*-\s*(\d{1,12})\b", text):
                candidates[prefix].append((block, match[1], match[2]))
        for prefix, matches in candidates.items():
            if not matches:
                continue
            ambiguous = len({(series, number) for _, series, number in matches}) > 1
            block, series, number = max(matches, key=lambda row: row[0].confidence)
            for key, value in (("series", series), ("number", number)):
                field = evidence(block, value)
                if ambiguous:
                    field.value = None
                    field.status = FieldStatus.ILLEGIBLE
                result.fields[f"{prefix}.{key}"] = field

    def _payment(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        if result.classification.family != "PAYMENT":
            return
        result.fields["vehicle.plate"] = ExtractedField(status=FieldStatus.NOT_APPLICABLE)
        amounts = []
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
            if result.fields["amounts.total"].status == FieldStatus.NOT_PRESENT and re.fullmatch(
                r"\s*(?:S/\.?|PEN|US\$|USD|EUR|€)\s*[\d.,]+\s*", text
            ):
                field = evidence(block, money(text))
                if field.value is None:
                    field.status = FieldStatus.ILLEGIBLE
                amounts.append(field)
        if amounts:
            result.fields["amounts.total"] = choose(amounts)

    def _date(self, ocr: OCRResult, result: ExtractedDocument) -> None:
        if result.fields["document.issue_date"].status != FieldStatus.NOT_PRESENT:
            return
        candidates = []
        for index, block in enumerate(ocr.blocks):
            if not re.fullmatch(r"\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}\s*", block.text):
                continue
            previous = ocr.blocks[index - 1] if index else None
            if previous and previous.page == block.page and re.search(
                r"\b(?:VENCIMIENTO|PAGO|TRASLADO|PERIODO|AFECTADO|REFERENCIA)\b",
                normalize(previous.text),
            ):
                continue
            parsed = parse_date(block.text)
            field = evidence(block, parsed.isoformat() if parsed else None)
            if not parsed:
                field.status = FieldStatus.ILLEGIBLE
            candidates.append(field)
        if candidates:
            result.fields["document.issue_date"] = choose(candidates)


def extract(ocr: OCRResult) -> ExtractedDocument:
    return LabelExtractor().extract(ocr)
