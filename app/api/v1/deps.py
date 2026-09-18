from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status

from app.core.auth import usuario_actual
from app.db.database import get_db
from app.domain.comprobante import Libro
from app.domain.periodo import MENSAJE_FORMATO, es_valido
from app.repositories import empresas as repo_empresas


async def empresa_actual(
    ruc: str = Path(..., description="RUC de la empresa"),
    _usuario: dict = Depends(usuario_actual),
    db=Depends(get_db),
) -> dict:
    """La empresa sobre la que se actúa, resuelta por el RUC del path.

    Antes esta dependencia comparaba el RUC del path contra el del token y
    devolvía 403 si no coincidían, porque el token identificaba a una empresa.
    Ahora identifica a una persona, y esa persona tiene acceso a todas las
    empresas registradas, así que lo único que queda por comprobar es que la
    empresa exista.

    El sujeto sigue saliendo del token —no del path—; lo que cambió es que el
    sujeto es quien pregunta y la empresa es el objeto sobre el que actúa.
    `_usuario` no se usa: está aquí por su efecto, que es imponer el 401/403
    antes de tocar Mongo.
    """
    empresa = await repo_empresas.obtener_por_ruc(db, ruc)
    if not empresa:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay ninguna empresa registrada con ese RUC",
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
