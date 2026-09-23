"""Clasificaciones frecuentes de una empresa: verlas, corregirlas y borrarlas."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.api.v1.deps import empresa_actual
from app.core.auth import usuario_actual
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.repositories import clasificaciones_frecuentes as repo_frecuentes
from app.repositories import plan_cuentas as repo_plan_cuentas
from app.schemas.comprobante import CuentaClasificada
from app.services import clasificacion_service

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_LARGO_CUENTA = 10


class ClasificacionFrecuente(BaseModel):
    id: str
    libro: str
    glosa: str
    cuenta_base: CuentaClasificada | None = None
    cuenta_total: CuentaClasificada | None = None
    clasificacion: str = ""
    subtipo: str = ""
    confianza: float = 0.0
    # Solo las confiables se reutilizan sin consultar a la IA.
    confiable: bool = False
    # `ia` o `usuario` (corregida o confirmada desde el panel).
    origen: str = "ia"
    usos: int = 0
    actualizado_en: datetime | None = None


class Correccion(BaseModel):
    cuenta_base: CuentaClasificada
    cuenta_total: CuentaClasificada | None = None

    @field_validator("cuenta_base", "cuenta_total")
    @classmethod
    def validar_codigo(cls, cuenta: CuentaClasificada | None) -> CuentaClasificada | None:
        if cuenta is None:
            return None
        codigo = cuenta.codigo.strip()
        if not codigo.isdigit() or len(codigo) > MAX_LARGO_CUENTA:
            raise ValueError(f"El código de cuenta son hasta {MAX_LARGO_CUENTA} dígitos")
        return cuenta.model_copy(update={"codigo": codigo})


def _salida(documento: dict[str, Any]) -> ClasificacionFrecuente:
    return ClasificacionFrecuente(id=str(documento["_id"]), **{
        k: v for k, v in documento.items() if k != "_id"
    })


@router.get("", response_model=list[ClasificacionFrecuente], summary="Clasificaciones frecuentes")
async def listar(
    libro: Libro | None = Query(None),
    empresa: dict = Depends(empresa_actual),
    db=Depends(get_db),
):
    entradas = await repo_frecuentes.listar(
        db, str(empresa["_id"]), libro.value if libro else None
    )
    return [_salida(e) for e in entradas]


@router.patch(
    "/{entrada_id}",
    response_model=ClasificacionFrecuente,
    summary="Corregir o confirmar una clasificación frecuente",
)
async def corregir(
    entrada_id: str,
    datos: Correccion,
    empresa: dict = Depends(empresa_actual),
    usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
):
    """Desde aquí la clasificación pasa a ser confiable: se reutiliza en los
    comprobantes con la misma glosa y se aplica a los que ya la usaban."""
    empresa_id = str(empresa["_id"])
    cambios: dict[str, Any] = {}
    for campo in ("cuenta_base", "cuenta_total"):
        cuenta: CuentaClasificada | None = getattr(datos, campo)
        if cuenta is None:
            continue
        # Sin descripción, la del maestro de cuentas de la empresa si la tiene.
        if not cuenta.descripcion:
            del_maestro = await repo_plan_cuentas.obtener(db, empresa_id, cuenta.codigo)
            if del_maestro:
                cuenta = cuenta.model_copy(update={"descripcion": del_maestro.get("descripcion")})
        cambios[campo] = cuenta.model_dump()

    entrada = await repo_frecuentes.corregir(db, empresa_id, entrada_id, cambios, usuario["email"])
    if entrada is None:
        raise HTTPException(status_code=404, detail="Clasificación frecuente no encontrada")
    aplicados = await clasificacion_service.aplicar_correccion(db, empresa_id, entrada)
    logger.info(
        "Clasificación frecuente %s corregida por %s: %s comprobantes actualizados",
        entrada_id, usuario["email"], aplicados,
    )
    return _salida(entrada)


@router.delete("/{entrada_id}", status_code=204, summary="Olvidar una clasificación frecuente")
async def eliminar(entrada_id: str, empresa: dict = Depends(empresa_actual), db=Depends(get_db)):
    """Los comprobantes ya clasificados conservan su cuenta; solo deja de reutilizarse."""
    if not await repo_frecuentes.eliminar(db, str(empresa["_id"]), entrada_id):
        raise HTTPException(status_code=404, detail="Clasificación frecuente no encontrada")
