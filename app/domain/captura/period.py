import re
from datetime import date

from app.domain.captura.models import PeriodDecision

MONTHS = (
    "ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE"
).split()


def parse_period(text: str, today: date | None = None) -> str | None:
    text = text.strip().upper()
    if today and text in {"1", "MES ACTUAL", "ACTUAL"}:
        return today.strftime("%Y%m")
    if today and text in {"2", "MES ANTERIOR", "ANTERIOR"}:
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        return f"{year:04d}{month:02d}"
    match = re.fullmatch(r"(20\d{2})[-/]?(0[1-9]|1[0-2])", text)
    if match:
        return "".join(match.groups())
    match = re.fullmatch(r"([A-Z]+)\s+(20\d{2})", text)
    if match and match[1] in MONTHS:
        return f"{match[2]}{MONTHS.index(match[1]) + 1:02d}"
    return None


def decide_period(
    ocr_date: date | None,
    confidence: float,
    metadata_date: date | None,
    target: str | None = None,
) -> PeriodDecision:
    """La fecha de recepción nunca participa en la asignación contable."""
    if target and parse_period(target) is None:
        raise ValueError("Periodo inválido")
    trusted = ocr_date is not None and confidence >= 0.85
    result = PeriodDecision(
        document_date=ocr_date if trusted else None,
        metadata_date=metadata_date,
        date_status="DATE_EXTRACTED" if trusted else "DATE_NOT_FOUND",
    )
    if trusted:
        detected = ocr_date.strftime("%Y%m")
        result.accounting_period = target or detected
        result.period_source = "BATCH_TARGET" if target else "OCR"
        result.period_validation = "MATCH"
        if target and target != detected:
            result.period_validation = "MISMATCH"
            result.date_status = "DATE_CONFLICT"
            result.issues.append("DATE_PERIOD_MISMATCH")
    elif target:
        result.accounting_period = target
        result.period_source = "BATCH_TARGET"
        result.issues.append("DATE_UNCERTAIN" if ocr_date or metadata_date else "DATE_NOT_FOUND")
        if metadata_date:
            result.date_status = "DATE_FROM_BATCH_PERIOD"
        elif ocr_date:
            result.date_status = "DATE_ILLEGIBLE"
    elif metadata_date:
        result.accounting_period = metadata_date.strftime("%Y%m")
        result.period_source = "METADATA"
        result.date_status = "DATE_FROM_METADATA"
        result.issues.append("DATE_UNCERTAIN")
    else:
        result.date_status = "DATE_ILLEGIBLE" if ocr_date else "DATE_NOT_FOUND"
        result.issues.append("PERIOD_REQUIRED")
    return result
