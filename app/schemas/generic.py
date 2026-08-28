from typing import Any

from pydantic import BaseModel


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
