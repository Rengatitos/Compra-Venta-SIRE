from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status

from app.core.auth import empresa_autenticada
from app.domain.comprobante import Libro
from app.domain.periodo import MENSAJE_FORMATO, es_valido


async def empresa_actual(
    ruc: str = Path(..., description="RUC de la empresa"),
    empresa: dict = Depends(empresa_autenticada),
) -> dict:
    if empresa.get("ruc") != ruc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El token no corresponde a esta empresa",
        )
    return empresa


def empresa_id(empresa: dict = Depends(empresa_actual)) -> str:
    return str(empresa["_id"])


def periodo_valido(
    periodo: str = Path(..., description="Periodo fiscal en formato YYYYMM"),
) -> str:
    if not es_valido(periodo):
        raise HTTPException(status_code=422, detail=MENSAJE_FORMATO)
    return periodo


def libro_valido(
    libro: str = Path(..., description="Libro electrónico: ventas o compras"),
) -> Libro:
    try:
        return Libro(libro)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="El libro debe ser 'ventas' o 'compras'",
        ) from None
