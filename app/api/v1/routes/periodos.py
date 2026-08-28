
from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import empresa_id, periodo_valido
from app.db.database import get_db
from app.repositories import comprobantes as repo_comprobantes
from app.repositories import periodos as repo_periodos
from app.schemas.generic import MessageResponse
from app.schemas.periodo import PeriodoCreate, PeriodoResponse, PeriodoUpdate

router = APIRouter()


@router.post("", response_model=PeriodoResponse, summary="Crear periodo")
async def crear_periodo(
    datos: PeriodoCreate,
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    if await repo_periodos.obtener(db, empresa, datos.periodo):
        raise HTTPException(status_code=409, detail="El periodo ya existe para esta empresa")

    creado = await repo_periodos.crear(db, empresa, datos.periodo)
    return {"periodo": creado["periodo"], "estado": creado["estado"]}


@router.get("", response_model=list[PeriodoResponse], summary="Listar periodos")
async def listar_periodos(empresa: str = Depends(empresa_id), db=Depends(get_db)):
    periodos = await repo_periodos.listar(db, empresa)
    return [{"periodo": p["periodo"], "estado": p["estado"]} for p in periodos]


@router.get("/{periodo}", response_model=PeriodoResponse, summary="Consultar periodo")
async def obtener_periodo(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    encontrado = await repo_periodos.obtener(db, empresa, periodo)
    if not encontrado:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")
    return {"periodo": encontrado["periodo"], "estado": encontrado["estado"]}


@router.put("/{periodo}", response_model=PeriodoResponse, summary="Actualizar estado del periodo")
async def actualizar_periodo(
    datos: PeriodoUpdate,
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    encontrado = await repo_periodos.obtener(db, empresa, periodo)
    if not encontrado:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")

    if datos.estado:
        await repo_periodos.actualizar_estado(db, empresa, periodo, datos.estado)
        return {"periodo": periodo, "estado": datos.estado}

    return {"periodo": encontrado["periodo"], "estado": encontrado["estado"]}


@router.delete("/{periodo}", response_model=MessageResponse, summary="Eliminar periodo")
async def eliminar_periodo(
    periodo: str = Depends(periodo_valido),
    empresa: str = Depends(empresa_id),
    db=Depends(get_db),
):
    await repo_comprobantes.eliminar_de_periodo(db, empresa, periodo)

    if await repo_periodos.eliminar(db, empresa, periodo) == 0:
        raise HTTPException(status_code=404, detail="Periodo no encontrado")

    return {"mensaje": "Periodo y comprobantes asociados eliminados"}
