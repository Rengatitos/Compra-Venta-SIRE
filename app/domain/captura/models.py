from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FieldStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    PRESENT_EMPTY = "PRESENT_EMPTY"
    NOT_PRESENT = "NOT_PRESENT"
    ILLEGIBLE = "ILLEGIBLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INFERRED = "INFERRED"


class ExtractedField(BaseModel):
    value: Any = None
    status: FieldStatus = FieldStatus.NOT_PRESENT
    confidence: float = 0
    raw_text: str | None = None
    source: str = "OCR"
    page: int | None = None
    bbox: list[list[float]] | None = None


class OCRBlock(BaseModel):
    text: str
    confidence: float = Field(ge=0, le=1)
    bbox: list[list[float]] = Field(default_factory=list)
    page: int = 1


class OCRResult(BaseModel):
    blocks: list[OCRBlock] = Field(default_factory=list)
    qr: list[str] = Field(default_factory=list)
    engine: str = "rapidocr"

    @property
    def text(self) -> str:
        return "\n".join(block.text for block in self.blocks)

    @property
    def confidence(self) -> float:
        return sum(b.confidence for b in self.blocks) / len(self.blocks) if self.blocks else 0


class Classification(BaseModel):
    family: str = "OTHER"
    type: str = "UNKNOWN"
    sunat_code: str | None = None
    confidence: float = 0


class ExtractedDocument(BaseModel):
    classification: Classification
    fields: dict[str, ExtractedField] = Field(default_factory=dict)
    items: list[dict[str, ExtractedField]] = Field(default_factory=list)


class PeriodDecision(BaseModel):
    document_date: date | None = None
    metadata_date: date | None = None
    accounting_period: str | None = None
    period_source: str | None = None
    date_status: str
    period_validation: str = "UNVERIFIED"
    issues: list[str] = Field(default_factory=list)


class SessionState(StrEnum):
    IDLE = "IDLE"
    WAITING_SINGLE_DOCUMENT = "WAITING_SINGLE_DOCUMENT"
    WAITING_SINGLE_CONFIRMATION = "WAITING_SINGLE_CONFIRMATION"
    BATCH_SELECTING_PERIOD = "BATCH_SELECTING_PERIOD"
    BATCH_RECEIVING = "BATCH_RECEIVING"
    BATCH_PROCESSING = "BATCH_PROCESSING"
    BATCH_REVIEW = "BATCH_REVIEW"
    BATCH_CONFIRMATION = "BATCH_CONFIRMATION"
    WAITING_CORRECTION = "WAITING_CORRECTION"


TERMINAL_STATUSES = {"READY", "NEEDS_REVIEW", "CONFIRMED", "FAILED", "CANCELLED", "EXPORTED"}
