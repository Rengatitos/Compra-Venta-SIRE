"""Alta de empresas, una a una o desde Excel, con sus datos de SUNAT.

Al recibir la carga se valida cada fila y las válidas se registran en el acto,
con la contraseña SOL cifrada como en cualquier alta. Lo lento, que es hablar
con SUNAT, queda como un trabajo `alta_empresa` por empresa en la cola durable,
así que el contador puede cerrar la página. Ese trabajo:

1. Si es de una carga masiva y la empresa no trae client_id, pide las
   credenciales del API SUNAT (`credenciales_sunat_service`). En la individual
   las pide el formulario justo después del alta, y pedirlas aquí también
   abriría dos sesiones SOL a la vez.
2. Pide el token de la API SIRE (`auth.renovar_token`). SUNAT declara en él el
   CIIU principal del contribuyente.
3. Consulta la ficha RUC pública (`ficha_ruc_service`): actividades económicas
   y, si el token no trajo CIIU, el de la actividad principal.
4. Guarda el CIIU y el rubro que se deriva de él.

Si algo de eso falla, la empresa se conserva. Un fallo pasajero se reintenta
por la cola; si persiste, la fila queda «agregada con observaciones».

La lectura del archivo es lo único que toca openpyxl; qué es una fila válida lo
decide `app.domain.carga_empresas`.
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils.exceptions import InvalidFileException
from pymongo.errors import DuplicateKeyError

from app.core.encryption import encrypt_password
from app.domain import rubro as dominio_rubro
from app.domain.carga_empresas import (
    MAX_FILAS,
    EstadoCarga,
    EstadoFila,
    FilaCarga,
    Modalidad,
    Motivo,
    ResultadoFila,
    validar_filas,
)
from app.domain.jobs import Job, TipoJob
from app.repositories import cargas_empresas as repo_cargas
from app.repositories import empresas as repo_empresas
from app.services import cola, ficha_ruc_service
from app.services.cola.errores import ErrorTransitorio
from app.services.sunat import auth

logger = logging.getLogger(__name__)

CABECERAS = ("Razón social", "RUC", "Usuario", "Contraseña")
CABECERAS_REPORTE = (
    "Fila", "RUC", "Razón social", "Usuario", "Estado", "Motivo", "Registrado por", "Fecha",
)
ETIQUETA_ESTADO = {
    EstadoFila.PENDIENTE.value: "En proceso",
    EstadoFila.AGREGADA.value: "Agregada",
    EstadoFila.CON_OBSERVACIONES.value: "Agregada con observaciones",
    EstadoFila.REQUIERE_CORRECCION.value: "Requiere corrección",
    EstadoFila.NO_AGREGADA.value: "No agregada",
}


class ExcelInvalido(ValueError):
    """El archivo no se puede leer como carga de empresas: lo arregla el usuario."""


# --- Excel -------------------------------------------------------------------


def _texto(valor: Any) -> str:
    """Una celda como texto. Excel guarda el RUC y las claves numéricas como
    número (`20123456789.0`), y así no se comparan con nada."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor).strip()


def _es_cabecera(celdas: list[str]) -> bool:
    ruc = celdas[1] if len(celdas) > 1 else ""
    return "RUC" in ruc.upper() or (bool(ruc) and not ruc.isdigit())


def leer_excel(contenido: bytes) -> list[FilaCarga]:
    """Filas de la primera hoja, columnas A a D. La cabecera es opcional."""
    if not contenido:
        raise ExcelInvalido("El archivo llegó vacío")
    try:
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as fallo:
        raise ExcelInvalido(f"No se pudo abrir el archivo como Excel: {fallo}") from fallo

    filas: list[FilaCarga] = []
    try:
        hoja = wb.worksheets[0]
        for numero, valores in enumerate(hoja.iter_rows(max_col=4, values_only=True), start=1):
            celdas = [_texto(v) for v in (list(valores) + [None] * 4)[:4]]
            if not any(celdas):
                continue
            if numero == 1 and _es_cabecera(celdas):
                continue
            filas.append(FilaCarga(numero, *celdas))
            if len(filas) > MAX_FILAS:
                raise ExcelInvalido(f"El archivo tiene más de {MAX_FILAS} empresas")
    finally:
        wb.close()

    if not filas:
        raise ExcelInvalido("El archivo no tiene ninguna empresa")
    return filas


def plantilla() -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.title = "Empresas"
    hoja.append(CABECERAS)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for columna, ancho in zip("ABCD", (40, 16, 16, 18), strict=True):
        hoja.column_dimensions[columna].width = ancho
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def reporte(carga: dict[str, Any]) -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.title = "Resultado"
    hoja.append(CABECERAS_REPORTE)
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for fila in carga.get("filas") or []:
        fecha = fila.get("fecha_registro")
        hoja.append([
            fila.get("fila"),
            fila.get("ruc"),
            fila.get("razon_social"),
            fila.get("usuario"),
            ETIQUETA_ESTADO.get(fila.get("estado"), fila.get("estado")),
            "; ".join(fila.get("motivos") or []),
            carga.get("registrado_por"),
            fecha.strftime("%d/%m/%Y %H:%M") if isinstance(fecha, datetime) else "",
        ])
    for columna, ancho in zip("ABCDEFGH", (6, 14, 36, 14, 26, 60, 28, 18), strict=True):
        hoja.column_dimensions[columna].width = ancho
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# --- Alta --------------------------------------------------------------------


@dataclass(frozen=True)
class CredencialesApi:
    client_id: str | None = None
    client_secret: str | None = None


def documento_empresa(
    fila: FilaCarga,
    *,
    modalidad: Modalidad,
    registrado_por: str,
    carga_id: str,
    credenciales: CredencialesApi,
) -> dict[str, Any]:
    return {
        "ruc": fila.ruc,
        "nombre": fila.razon_social or None,
        "usuario": fila.usuario,
        "password": encrypt_password(fila.password),
        "sunat_token": None,
        "sunat_client_id": credenciales.client_id,
        "sunat_client_secret": credenciales.client_secret,
        "correos_notificacion": [],
        "registro": {
            "modalidad": modalidad.value,
            "por": registrado_por,
            "fecha": datetime.now(UTC),
            "carga_id": carga_id,
        },
    }


async def registrar(
    db,
    filas: list[FilaCarga],
    *,
    modalidad: Modalidad,
    registrado_por: str,
    archivo: str | None = None,
    credenciales: CredencialesApi = CredencialesApi(),
) -> dict[str, Any]:
    """Valida, crea las empresas válidas y encola el resto del alta.

    Devuelve la carga tal como queda en Mongo, con `_id` como texto.
    """
    existentes = await repo_empresas.rucs_existentes(db, [f.ruc for f in filas if f.ruc])
    validadas = validar_filas(
        filas, existentes, exigir_razon_social=modalidad is Modalidad.MASIVA
    )
    resultados = [
        ResultadoFila(
            fila=fila.fila,
            ruc=fila.ruc,
            razon_social=fila.razon_social,
            usuario=fila.usuario,
            estado=EstadoFila.NO_AGREGADA if motivos else EstadoFila.PENDIENTE,
            motivos=[m.value for m in motivos] or [Motivo.EN_PROCESO.value],
        )
        for fila, motivos in validadas
    ]
    carga_id = await repo_cargas.crear(db, {
        "modalidad": modalidad.value,
        "archivo": archivo,
        "registrado_por": registrado_por,
        "estado": EstadoCarga.EN_PROGRESO.value,
        "progreso": {"actual": 0, "total": len(resultados), "mensaje": "Registrando"},
        "creado_en": datetime.now(UTC),
        "terminado_en": None,
        "filas": [r.a_documento() for r in resultados],
    })

    for fila, motivos in validadas:
        if motivos:
            continue
        try:
            empresa = await repo_empresas.crear(db, documento_empresa(
                fila,
                modalidad=modalidad,
                registrado_por=registrado_por,
                carga_id=carga_id,
                credenciales=credenciales,
            ))
        except DuplicateKeyError:
            # Otra persona la dio de alta entre la validación y aquí.
            await repo_cargas.guardar_fila(db, carga_id, fila.fila, {
                "estado": EstadoFila.NO_AGREGADA.value,
                "motivos": [Motivo.RUC_EXISTENTE.value],
            })
            continue
        await repo_cargas.guardar_fila(db, carga_id, fila.fila, {
            "empresa_id": str(empresa["_id"]),
            "fecha_registro": datetime.now(UTC),
        })
        await cola.encolar(
            db,
            TipoJob.ALTA_EMPRESA,
            fila.ruc,
            "",
            cola=cola.carril_sol(fila.ruc),
            parametros={
                "carga_id": carga_id,
                "fila": fila.fila,
                "obtener_credenciales": modalidad is Modalidad.MASIVA,
            },
        )

    await repo_cargas.recalcular(db, carga_id)
    logger.info(
        "Carga %s (%s) de %s: %s filas, %s válidas",
        carga_id, modalidad.value, registrado_por, len(filas),
        sum(1 for _, motivos in validadas if not motivos),
    )
    carga = await repo_cargas.obtener(db, carga_id)
    return carga


@dataclass
class Completado:
    observaciones: list[str]
    # Algún fallo puede ser pasajero (SUNAT no respondió): vale la pena otro
    # intento. Una clave SOL rechazada no lo es.
    reintentable: bool
    # Terminó sin client_id/secret: sin ellos la empresa no descarga el SIRE.
    sin_credenciales: bool = False


async def completar(db, empresa: dict[str, Any], *, obtener_credenciales: bool) -> Completado:
    """Pasos 1 a 4 del alta. Nunca lanza: lo que no sale queda como observación."""
    from app.services import credenciales_sunat_service
    from app.services.scraping_sunat import CredencialesSolError
    from app.services.sunat.credenciales_api import SinRecursoSire

    observaciones: list[str] = []
    reintentable = False
    ruc = empresa["ruc"]

    tiene_credenciales = empresa.get("sunat_client_id") and empresa.get("sunat_client_secret")
    if obtener_credenciales and not tiene_credenciales:
        try:
            await credenciales_sunat_service.obtener(db, empresa)
            empresa = await repo_empresas.obtener_por_ruc(db, ruc) or empresa
        except CredencialesSolError:
            observaciones.append(f"{Motivo.ERROR_SUNAT.value}: clave SOL rechazada")
            # Sin clave válida el resto también fallaría y reintentar podría
            # bloquear el usuario en SUNAT. La ficha RUC es pública: sigue.
        except SinRecursoSire as fallo:
            observaciones.append(f"{Motivo.ERROR_SUNAT.value}: {fallo}")
        except Exception as fallo:
            reintentable = True
            logger.warning("Credenciales de API no obtenidas ruc=%s: %s", ruc, fallo)
            observaciones.append(
                f"{Motivo.ERROR_SUNAT.value}: no se obtuvieron las credenciales de API ({fallo})"
            )

    ciiu = ""
    if empresa.get("sunat_client_id") and empresa.get("sunat_client_secret"):
        token, error = await auth.renovar_token(db, empresa)
        if token:
            ciiu = dominio_rubro.ciiu_desde_token_sunat(token)
        else:
            reintentable = True
            observaciones.append(f"{Motivo.ERROR_SUNAT.value}: sin token de la API SIRE ({error})")

    try:
        empresa = await ficha_ruc_service.actualizar_empresa(db, empresa) or empresa
    except Exception as fallo:
        logger.warning("Ficha RUC no obtenida ruc=%s: %s", ruc, fallo)
        if not ciiu:
            reintentable = True
            observaciones.append(f"{Motivo.ERROR_CIIU.value}: {fallo}")
    else:
        if not ciiu:
            ciiu = ciiu_principal(empresa.get("actividades_economicas") or [])
        if not ciiu:
            observaciones.append(f"{Motivo.ERROR_CIIU.value}: la ficha RUC no trae actividades")

    cambios: dict[str, Any] = {}
    if ciiu:
        cambios["ciiu"] = ciiu
        cambios["rubro"] = dominio_rubro.desde_ciiu(ciiu)
    razon_social = (empresa.get("ficha_ruc") or {}).get("razon_social")
    if not empresa.get("nombre") and razon_social:
        cambios["nombre"] = razon_social
    if cambios:
        await repo_empresas.actualizar(db, empresa["_id"], cambios)
    sin_credenciales = not (empresa.get("sunat_client_id") and empresa.get("sunat_client_secret"))
    return Completado(observaciones, reintentable, sin_credenciales)


def ciiu_principal(actividades: list[dict[str, Any]]) -> str:
    principal = next(
        (a for a in actividades if str(a.get("tipo") or "").upper() == "PRINCIPAL"), None
    )
    elegida = principal or (actividades[0] if actividades else None)
    return str((elegida or {}).get("ciiu") or "")


async def alta_empresa(db, job: Job, reportar) -> dict[str, Any]:
    """Manejador de la cola para `alta_empresa`."""
    from app.services.cola.tareas import empresa_de

    carga_id = job.parametros.get("carga_id")
    fila = job.parametros.get("fila")
    empresa = await empresa_de(db, job)
    await reportar(0, 1, "Completando los datos de SUNAT")
    completado = await completar(
        db, empresa, obtener_credenciales=bool(job.parametros.get("obtener_credenciales"))
    )

    if completado.reintentable and job.intentos < job.max_intentos:
        if carga_id and fila is not None:
            await repo_cargas.guardar_fila(db, carga_id, fila, {
                "motivos": [
                    f"{Motivo.EN_PROCESO.value} (reintento {job.intentos} de "
                    f"{job.max_intentos - 1})",
                    *completado.observaciones,
                ],
            })
        raise ErrorTransitorio("; ".join(completado.observaciones))

    if job.parametros.get("obtener_credenciales") and completado.sin_credenciales:
        estado = EstadoFila.REQUIERE_CORRECCION
    elif completado.observaciones:
        estado = EstadoFila.CON_OBSERVACIONES
    else:
        estado = EstadoFila.AGREGADA
    if carga_id and fila is not None:
        await repo_cargas.guardar_fila(db, carga_id, fila, {
            "estado": estado.value,
            "motivos": completado.observaciones or [Motivo.REGISTRO_EXITOSO.value],
        })
    await reportar(1, 1, "Alta completada")
    return {"estado": estado.value, "observaciones": completado.observaciones}
