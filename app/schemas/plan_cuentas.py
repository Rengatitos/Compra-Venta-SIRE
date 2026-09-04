from pydantic import BaseModel


class CuentaResponse(BaseModel):
    cuenta: str
    descripcion: str
    tipo: str
    analisis: str
    centro_costos: str
    # 1 = elemento, 2 = cuenta, 3 = subcuenta y divisionarias. Lo usa el
    # frontend para sangrar la tabla como en el archivo original.
    nivel: int


class PlanCuentasResponse(BaseModel):
    cuentas: list[CuentaResponse]
    # Total que casa con el filtro, no el de la página: es lo que permite
    # paginar y mostrar "N de M" sin una segunda llamada.
    total: int


class CargaResponse(BaseModel):
    mensaje: str
    cuentas: int
