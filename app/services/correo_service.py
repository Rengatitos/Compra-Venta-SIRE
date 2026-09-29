"""Correo final de una solicitud: aviso de que terminó, con el ZIP o un enlace.

Lo recibe solo quien pidió la solicitud (el administrador que entró con su
cuenta de Google), con todas sus empresas. Los `correos_notificacion` de cada
empresa ya no se usan.

El servidor SMTP, el remitente, la lista blanca y la plantilla se configuran en
el panel (`/correos`) y se leen de Mongo en cada envío
(`app.repositories.configuracion`). Un destinatario fuera de la lista blanca
queda «bloqueado» y no se le escribe: en local solo se admite el correo de
pruebas. Si el ZIP pasa del tamaño máximo, en vez de adjuntarlo se manda un
enlace firmado que caduca.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
from pathlib import Path
from typing import Any

from app.core.auth import crear_token_descarga
from app.core.config import settings
from app.core.encryption import decrypt_password
from app.domain.configuracion_correo import (
    ConfiguracionCorreo,
    Valor,
    renderizar_html,
    renderizar_texto,
)
from app.domain.jobs import Job
from app.domain.solicitudes import (
    EstadoEnvio,
    EstadoItem,
    EstadoPaso,
    ModoEnvio,
    Paso,
    fecha_peru,
    nombre_zip,
)
from app.repositories import configuracion as repo_configuracion
from app.repositories import empresas as repo_empresas
from app.repositories import solicitudes as repo_solicitudes
from app.services import empaquetado_service
from app.services.cola.errores import ErrorPermanente, ErrorTransitorio

logger = logging.getLogger(__name__)

TIMEOUT_ENVIO_S = 60
TIMEOUT_PRUEBA_S = 20

ETIQUETA_ITEM = {
    EstadoItem.COMPLETADO.value: "Completado",
    EstadoItem.CON_ERRORES.value: "Completado con observaciones",
    EstadoItem.FALLIDO.value: "Con error",
    EstadoItem.PENDIENTE.value: "Pendiente",
    EstadoItem.EN_PROGRESO.value: "En proceso",
}
ETAPAS = (
    ("Descarga de reportes SIRE", {Paso.SIRE_COMPRAS, Paso.SIRE_VENTAS}),
    ("Descarga de comprobantes", {Paso.DETALLE_COMPRAS, Paso.DETALLE_VENTAS}),
    ("Procesamiento y clasificación con IA", {
        Paso.CLASIFICACION_COMPRAS, Paso.CLASIFICACION_VENTAS,
    }),
)


class CorreoNoEnviado(Exception):
    """El envío de prueba falló; el mensaje ya viene en palabras del usuario."""


async def destinatarios(db, solicitud: dict[str, Any]) -> list[dict[str, Any]]:
    """Un solo envío: a quien pidió la solicitud, con todas sus empresas."""
    items = solicitud["items"]
    rucs = sorted({item["ruc"] for item in items})
    empresas = []
    for ruc in rucs:
        empresa = await repo_empresas.obtener_por_ruc(db, ruc) or {}
        empresas.append({"ruc": ruc, "nombre": empresa.get("nombre")})
    return [{
        "correo": solicitud["creado_por"].lower(),
        "rucs": rucs,
        "empresas": empresas,
        "periodos": sorted({i["periodo"] for i in items}),
        "estado": EstadoEnvio.PENDIENTE.value,
        "modo": None,
        "intentos": 0,
        "error": None,
        "creado_en": datetime.now(UTC),
        "enviado_en": None,
    }]


def password_smtp(config: ConfiguracionCorreo) -> str:
    """La guardada desde el panel o, si no hay, la de `CORREO_SMTP_PASSWORD`."""
    password = (
        decrypt_password(config.password_cifrada)
        if config.password_cifrada
        else settings.CORREO_SMTP_PASSWORD or ""
    )
    # Google muestra la contraseña de aplicación en bloques («abcd efgh ...»);
    # los espacios no son parte de ella.
    if config.host.endswith("gmail.com"):
        password = password.replace(" ", "")
    return password


def listo(config: ConfiguracionCorreo) -> bool:
    """Hay servidor y, si pide usuario, también contraseña."""
    return config.configurado and (not config.usuario or bool(password_smtp(config)))


FALTA_CONFIGURAR = "Falta la contraseña de aplicación del correo remitente: guárdala en «Correos»"


# --- Mensaje -------------------------------------------------------------------


def _estado_etapa(items: list[dict[str, Any]], pasos: set[Paso]) -> str:
    estados = [
        p["estado"]
        for item in items
        for p in item.get("pasos") or []
        if Paso(p["paso"]) in pasos
    ]
    if not estados or all(e == EstadoPaso.OMITIDO.value for e in estados):
        return "omitido"
    if any(e == EstadoPaso.FALLIDO.value for e in estados):
        return "con errores"
    return "completado"


def _mes(periodo: str) -> str:
    return f"{periodo[4:]}/{periodo[:4]}"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def valores(
    solicitud: dict[str, Any],
    envio: dict[str, Any],
    config: ConfiguracionCorreo,
    *,
    adjunto: bool,
    enlace: str | None,
) -> dict[str, Valor]:
    """Lo que pone cada variable de la plantilla para este destinatario."""
    items = [i for i in solicitud["items"] if i["ruc"] in envio["rucs"]]
    nombres = {e["ruc"]: e.get("nombre") or e["ruc"] for e in envio["empresas"]}
    etapas = [(nombre, _estado_etapa(items, pasos)) for nombre, pasos in ETAPAS]
    etapas.append(("Generación de los archivos finales", "completado"))

    if adjunto:
        entrega = Valor(
            "Adjuntamos el ZIP con los reportes y comprobantes de cada empresa y periodo."
        )
    elif enlace:
        entrega = Valor(
            f"El ZIP pesa más de lo que admite el correo; descárgalo aquí (válido "
            f"{config.dias_enlace} días): {enlace}",
            f'El ZIP pesa más de lo que admite el correo: <a href="{escape(enlace)}">'
            f"descárgalo aquí</a> (válido {config.dias_enlace} días).",
        )
    else:
        entrega = Valor(
            "El ZIP pesa más de lo que admite el correo; descárgalo desde el panel de Sire."
        )

    filas = [
        (
            nombres[i["ruc"]],
            i["ruc"],
            _mes(i["periodo"]),
            ETIQUETA_ITEM.get(i["estado"], i["estado"]),
        )
        for i in items
    ]
    tabla = (
        '<table cellpadding="6" style="border-collapse:collapse" border="1">'
        "<tr><th>Empresa</th><th>RUC</th><th>Periodo</th><th>Estado</th></tr>"
        + "".join(
            "<tr>" + "".join(f"<td>{escape(c)}</td>" for c in fila) + "</tr>" for fila in filas
        )
        + "</table>"
    )
    periodos = sorted({i["periodo"] for i in items})
    return {
        "destinatario": Valor(envio["correo"]),
        "resumen": Valor(
            f"{_plural(len(envio['rucs']), 'empresa', 'empresas')}, "
            f"{_plural(len(items), 'periodo', 'periodos')}"
        ),
        "empresas": Valor(", ".join(nombres[r] for r in envio["rucs"])),
        "periodos": Valor(", ".join(_mes(p) for p in periodos)),
        "fecha": Valor(fecha_peru(solicitud.get("terminado_en")).strftime("%d/%m/%Y")),
        "etapas": Valor(
            "\n".join(f"- {nombre}: {estado}" for nombre, estado in etapas),
            "<ul>" + "".join(
                f"<li>{escape(nombre)}: <strong>{escape(estado)}</strong></li>"
                for nombre, estado in etapas
            ) + "</ul>",
        ),
        "resultados": Valor(
            "\n".join(f"- {n} ({r}) · {p}: {e}" for n, r, p, e in filas), tabla
        ),
        "entrega": entrega,
    }


def construir(
    solicitud: dict[str, Any],
    envio: dict[str, Any],
    config: ConfiguracionCorreo,
    *,
    adjunto: Path | None,
    enlace: str | None,
) -> EmailMessage:
    datos = valores(solicitud, envio, config, adjunto=adjunto is not None, enlace=enlace)
    mensaje = EmailMessage()
    # Un salto de línea en el asunto rompería la cabecera.
    mensaje["Subject"] = " ".join(renderizar_texto(config.plantilla_asunto, datos).split())
    mensaje["From"] = config.remitente
    mensaje["To"] = envio["correo"]
    mensaje.set_content(renderizar_texto(config.plantilla_cuerpo, datos))
    mensaje.add_alternative(renderizar_html(config.plantilla_cuerpo, datos), subtype="html")
    if adjunto:
        mensaje.add_attachment(
            adjunto.read_bytes(), maintype="application", subtype="zip", filename=adjunto.name
        )
    return mensaje


# Datos de ejemplo para la vista previa del panel y el correo de prueba.
SOLICITUD_EJEMPLO: dict[str, Any] = {
    "_id": "ejemplo",
    "creado_por": "contador@ejemplo.pe",
    "terminado_en": None,
    "items": [
        {"ruc": "20123456789", "periodo": "202608", "estado": "completado", "pasos": [
            {"paso": "sire_compras", "estado": "completado"},
            {"paso": "detalle_compras", "estado": "completado"},
            {"paso": "clasificacion_compras", "estado": "completado"},
        ]},
        {"ruc": "20987654321", "periodo": "202608", "estado": "con_errores", "pasos": [
            {"paso": "sire_compras", "estado": "completado"},
            {"paso": "detalle_compras", "estado": "fallido"},
            {"paso": "clasificacion_compras", "estado": "completado"},
        ]},
    ],
}
ENVIO_EJEMPLO: dict[str, Any] = {
    "correo": "contador@ejemplo.pe",
    "rucs": ["20123456789", "20987654321"],
    "empresas": [
        {"ruc": "20123456789", "nombre": "Empresa Alfa SAC"},
        {"ruc": "20987654321", "nombre": "Comercial Beta EIRL"},
    ],
}


def vista_previa(config: ConfiguracionCorreo) -> dict[str, str]:
    datos = valores(SOLICITUD_EJEMPLO, ENVIO_EJEMPLO, config, adjunto=True, enlace=None)
    return {
        "asunto": " ".join(renderizar_texto(config.plantilla_asunto, datos).split()),
        "texto": renderizar_texto(config.plantilla_cuerpo, datos),
        "html": renderizar_html(config.plantilla_cuerpo, datos),
    }


# --- SMTP ----------------------------------------------------------------------


def _seguridad(config: ConfiguracionCorreo) -> str:
    """El 465 es SSL implícito siempre: con STARTTLS o sin cifrar, el servidor
    corta la conexión («Connection unexpectedly closed»). Una configuración
    guardada con esa mezcla se corrige aquí en vez de fallar."""
    return "ssl" if config.puerto == 465 else config.seguridad


def _enviar(mensaje: EmailMessage, config: ConfiguracionCorreo, timeout: int = TIMEOUT_ENVIO_S):
    seguridad = _seguridad(config)
    if seguridad == "ssl":
        smtp = smtplib.SMTP_SSL(config.host, config.puerto, timeout=timeout)
    else:
        smtp = smtplib.SMTP(config.host, config.puerto, timeout=timeout)
    with smtp:
        if seguridad == "starttls":
            smtp.starttls()
        if config.usuario:
            smtp.login(config.usuario, password_smtp(config))
        smtp.send_message(mensaje)


def _explicar(exc: Exception) -> tuple[str, bool]:
    """Mensaje para el usuario y si es definitivo (reintentar no lo arregla)."""
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "El servidor de correo rechazó el usuario o la contraseña (SMTP)", True
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return (
            "El servidor de correo cortó la conexión: revisa en «Opciones avanzadas» que el "
            "puerto y la seguridad coincidan (Gmail: 587 con STARTTLS o 465 con SSL/TLS)"
        ), False
    if isinstance(exc, smtplib.SMTPRecipientsRefused | smtplib.SMTPSenderRefused):
        return f"El servidor de correo rechazó la dirección: {exc}", True
    if isinstance(exc, TimeoutError | ConnectionError | OSError) and not isinstance(
        exc, smtplib.SMTPException
    ):
        return f"No se pudo conectar con el servidor de correo: {exc}", False
    return str(exc)[:500] or type(exc).__name__, False


async def enviar_prueba(db, destinatario: str) -> None:
    """Un correo de prueba con la configuración guardada. Lanza `CorreoNoEnviado`."""
    config = await repo_configuracion.obtener_correo(db)
    if not listo(config):
        raise CorreoNoEnviado(FALTA_CONFIGURAR)
    if not config.permitido(destinatario):
        raise CorreoNoEnviado("Ese destinatario no está en la lista de destinatarios permitidos")
    previa = vista_previa(config)
    mensaje = EmailMessage()
    mensaje["Subject"] = f"[Prueba] {previa['asunto']}"
    mensaje["From"] = config.remitente
    mensaje["To"] = destinatario
    mensaje.set_content(
        "Correo de prueba de Sire con datos de ejemplo.\n\n" + previa["texto"]
    )
    mensaje.add_alternative(
        "<p><em>Correo de prueba de Sire con datos de ejemplo.</em></p>" + previa["html"],
        subtype="html",
    )
    try:
        await asyncio.to_thread(_enviar, mensaje, config, TIMEOUT_PRUEBA_S)
    except Exception as exc:
        raise CorreoNoEnviado(_explicar(exc)[0]) from exc


# --- Manejador de la cola ------------------------------------------------------


async def _zip_para(db, solicitud: dict[str, Any], envio: dict[str, Any]) -> Path:
    """El ZIP completo, o uno con solo las empresas de este destinatario."""
    raiz = empaquetado_service.raiz_solicitud(str(solicitud["_id"]))
    completo = raiz / solicitud["zip"]["archivo"]
    todas = sorted({i["ruc"] for i in solicitud["items"]})
    if envio["rucs"] == todas:
        return completo
    huella = hashlib.sha256(",".join(envio["rucs"]).encode()).hexdigest()[:10]
    parcial = raiz / nombre_zip(solicitud["creado_en"]).replace(".zip", f"_{huella}.zip")
    if not parcial.is_file():
        items = [i for i in solicitud["items"] if i["ruc"] in envio["rucs"]]
        await empaquetado_service.armar_zip(db, items, parcial)
    return parcial


def _enlace(solicitud_id: str, archivo: str, config: ConfiguracionCorreo) -> str | None:
    if not config.url_publica:
        return None
    token = crear_token_descarga(solicitud_id, archivo, config.dias_enlace)
    return f"{config.url_publica.rstrip('/')}{settings.API_V1_PREFIX}/descargas/{token}"


async def enviar_solicitud(db, job: Job, reportar) -> dict[str, Any]:
    """Manejador de la cola para `envio_correo`."""
    solicitud_id = job.solicitud_id or ""
    solicitud = await repo_solicitudes.obtener(db, solicitud_id)
    if not solicitud:
        raise ErrorPermanente("La solicitud ya no existe")
    config = await repo_configuracion.obtener_correo(db)

    envios = solicitud.get("envios") or []
    if not envios:
        envios = await destinatarios(db, solicitud)
        await repo_solicitudes.actualizar(db, solicitud_id, {"envios": envios})

    pendientes_reintentables = 0
    for indice, envio in enumerate(envios):
        if envio["estado"] in (EstadoEnvio.ENVIADO.value, EstadoEnvio.BLOQUEADO.value):
            continue
        if envio["estado"] == EstadoEnvio.FALLIDO.value and envio.get("definitivo"):
            continue
        await reportar(indice, len(envios), f"Enviando a {envio['correo']}")
        cambios: dict[str, Any]
        if not config.permitido(envio["correo"]):
            cambios = {
                "estado": EstadoEnvio.BLOQUEADO.value,
                "error": "Destinatario fuera de la lista de destinatarios permitidos",
            }
        elif not listo(config):
            cambios = {
                "estado": EstadoEnvio.FALLIDO.value,
                "definitivo": True,
                "error": FALTA_CONFIGURAR,
            }
        else:
            cambios = await _enviar_uno(db, solicitud, envio, config)
            if cambios["estado"] == EstadoEnvio.FALLIDO.value and not cambios.get("definitivo"):
                pendientes_reintentables += 1
        await repo_solicitudes.guardar_envio(db, solicitud_id, indice, cambios)
        envio.update(cambios)

    await reportar(len(envios), len(envios), "Envíos terminados")
    if pendientes_reintentables and job.intentos < job.max_intentos:
        raise ErrorTransitorio(f"{pendientes_reintentables} correos no se pudieron enviar")
    return {
        "enviados": sum(e["estado"] == EstadoEnvio.ENVIADO.value for e in envios),
        "bloqueados": sum(e["estado"] == EstadoEnvio.BLOQUEADO.value for e in envios),
        "fallidos": sum(e["estado"] == EstadoEnvio.FALLIDO.value for e in envios),
    }


async def _enviar_uno(
    db, solicitud: dict[str, Any], envio: dict[str, Any], config: ConfiguracionCorreo
) -> dict[str, Any]:
    intentos = envio.get("intentos", 0) + 1
    try:
        zip_ = await _zip_para(db, solicitud, envio)
        adjunto = zip_ if zip_.stat().st_size <= config.max_adjunto_mb * 1024 * 1024 else None
        enlace = None if adjunto else _enlace(str(solicitud["_id"]), zip_.name, config)
        mensaje = construir(solicitud, envio, config, adjunto=adjunto, enlace=enlace)
        await asyncio.to_thread(_enviar, mensaje, config)
    except Exception as exc:
        error, definitivo = _explicar(exc)
        logger.warning("No se pudo enviar el correo a %s: %s", envio["correo"], error)
        return {
            "estado": EstadoEnvio.FALLIDO.value,
            "definitivo": definitivo,
            "intentos": intentos,
            "error": error,
        }
    logger.info("Correo enviado a %s (%s)", envio["correo"], "adjunto" if adjunto else "enlace")
    return {
        "estado": EstadoEnvio.ENVIADO.value,
        "modo": (ModoEnvio.ADJUNTO if adjunto else ModoEnvio.ENLACE).value,
        "intentos": intentos,
        "error": None,
        "enviado_en": datetime.now(UTC),
    }
