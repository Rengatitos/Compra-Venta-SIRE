from pydantic import BaseModel

from app.schemas.generic import FechaUtc
from app.schemas.job import JobResponse


class ProcesosPorEstado(BaseModel):
    pendiente: int = 0
    en_progreso: int = 0
    completado: int = 0
    fallido: int = 0


class PeriodoResumen(BaseModel):
    periodo: str
    estado: str | None = None


class ResumenEmpresa(BaseModel):
    ruc: str
    nombre: str | None = None
    correos_notificacion: list[str] = []
    total_periodos: int = 0
    periodos: list[PeriodoResumen] = []
    ultima_actualizacion_sire: FechaUtc | None = None
    ultimo_proceso: JobResponse | None = None
    procesos_por_estado: ProcesosPorEstado
    # `lista`, `registrando` o `requiere_correccion` (sin credenciales del API
    # SUNAT: no se puede abrir hasta corregirla).
    estado_alta: str = "lista"
    motivo_alta: str | None = None


class ResumenEmpresas(BaseModel):
    total_empresas: int
    # Ventana, en días, de los procesos terminados que se cuentan.
    dias: int
    procesos_por_estado: ProcesosPorEstado
    empresas: list[ResumenEmpresa]
