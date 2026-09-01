from fastapi import APIRouter

from app.api.v1.routes import (
    analisis,
    analytics,
    auth,
    comprobantes,
    detalle,
    empresas,
    jobs,
    periodos,
    propuesta,
    referencias,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(empresas.router, prefix="/empresas", tags=["Empresas"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])

api_router.include_router(
    referencias.router,
    prefix="/empresas/{ruc}/referencias",
    tags=["Referencias"],
)
api_router.include_router(
    periodos.router,
    prefix="/empresas/{ruc}/periodos",
    tags=["Periodos"],
)
api_router.include_router(
    propuesta.router,
    prefix="/empresas/{ruc}/periodos/{periodo}",
    tags=["Propuesta SIRE"],
)
api_router.include_router(
    comprobantes.router,
    prefix="/empresas/{ruc}/periodos/{periodo}/comprobantes",
    tags=["Comprobantes"],
)
# `libro` va en el path, no como filtro opcional: la extracción y el análisis
# se comportan distinto en ventas y en compras, y un árbol de rutas por libro
# garantizaría que las dos ramas divergieran.
api_router.include_router(
    analisis.router,
    prefix="/empresas/{ruc}/periodos/{periodo}/libros/{libro}/analisis",
    tags=["Análisis IA"],
)
api_router.include_router(
    detalle.router,
    prefix="/empresas/{ruc}/periodos/{periodo}/libros/{libro}/detalle",
    tags=["Detalle SUNAT"],
)
