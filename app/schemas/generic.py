from pydantic import BaseModel
from typing import Any, List, Optional

class MessageResponse(BaseModel):
    mensaje: str

class StatusResponse(BaseModel):
    estado: str
    mensaje: Optional[str] = None
    datos: Optional[Any] = None

class FileListResponse(BaseModel):
    archivos: List[str]

class DataResponse(BaseModel):
    data: Any

class TemasResponse(BaseModel):
    temas: List[str]

class SireResponse(StatusResponse):
    facturas_guardadas: int
