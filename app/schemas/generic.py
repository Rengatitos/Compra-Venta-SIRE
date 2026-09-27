from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel


def _utc(valor: datetime | None) -> datetime | None:
    # Mongo devuelve las fechas sin zona; son UTC. Sin marcarlas, la API las
    # serializa sin `Z` y el navegador las lee como hora local.
    if valor is None or valor.tzinfo is not None:
        return valor
    return valor.replace(tzinfo=UTC)


FechaUtc = Annotated[datetime, AfterValidator(_utc)]


class MessageResponse(BaseModel):
    mensaje: str


class StatusResponse(BaseModel):
    estado: str
    mensaje: str | None = None
    datos: Any | None = None


class FileListResponse(BaseModel):
    archivos: list[str]


class DataResponse(BaseModel):
    data: Any


class TemasResponse(BaseModel):
    temas: list[str]
