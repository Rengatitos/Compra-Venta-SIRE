"""Correo final de una solicitud: aviso de que terminó, con el ZIP o un enlace.

Recibe el correo:

- el contador que pidió la solicitud, con todas sus empresas;
- cada dirección de `correos_notificacion` de las empresas incluidas, solo con
  las empresas a las que está asociada. Es un cliente del contador y no debe
  ver los archivos de los demás, así que recibe un ZIP propio.

Un destinatario fuera de `CORREO_DESTINATARIOS_PERMITIDOS` queda «bloqueado» y
no se le escribe: en local solo se admite el correo de pruebas. El envío es
SMTP (`smtplib`, en un hilo). Si el ZIP pasa de `CORREO_MAX_ADJUNTO_MB`, en vez
de adjuntarlo se manda un enlace firmado que caduca.
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
from app.domain.jobs import Job
from app.domain.solicitudes import (
    EstadoEnvio,
    EstadoItem,
    EstadoPaso,
    ModoEnvio,
    Paso,
    nombre_zip,
)
from app.repositories import empresas as repo_empresas
from app.repositories import solicitudes as repo_solicitudes
from app.services import empaquetado_service
from app.services.cola.errores import ErrorPermanente, ErrorTransitorio

logger = logging.getLogger(__name__)

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


def smtp_configurado() -> bool:
    return bool(settings.SMTP_HOST)


def permitido(correo: str) -> bool:
    lista = settings.CORREO_DESTINATARIOS_PERMITIDOS
    return not lista or correo.lower() in lista


async def destinatarios(db, solicitud: dict[str, Any]) -> list[dict[str, Any]]:
    """Un envío por dirección, con las empresas y periodos que le tocan."""
    items = solicitud["items"]
    todas = sorted({item["ruc"] for item in items})
    por_correo: dict[str, set[str]] = {solicitud["creado_por"].lower(): set(todas)}
    nombres: dict[str, str | None] = {}
    for ruc in todas:
        empresa = await repo_empresas.obtener_por_ruc(db, ruc) or {}
        nombres[ruc] = empresa.get("nombre")
        for correo in empresa.get("correos_notificacion") or []:
            por_correo.setdefault(correo.lower(), set()).add(ruc)

    envios = []
    for correo, rucs in por_correo.items():
        periodos = sorted({i["periodo"] for i in items if i["ruc"] in rucs})
        envios.append({
            "correo": correo,
            "rucs": sorted(rucs),
            "empresas": [{"ruc": r, "nombre": nombres.get(r)} for r in sorted(rucs)],
            "periodos": periodos,
            "estado": EstadoEnvio.PENDIENTE.value,
            "modo": None,
            "intentos": 0,
            "error": None,
            "creado_en": datetime.now(UTC),
            "enviado_en": None,
        })
    return envios


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


def construir(
    solicitud: dict[str, Any],
    envio: dict[str, Any],
    *,
    adjunto: Path | None,
    enlace: str | None,
) -> EmailMessage:
    items = [i for i in solicitud["items"] if i["ruc"] in envio["rucs"]]
    nombres = {e["ruc"]: e.get("nombre") or e["ruc"] for e in envio["empresas"]}
    etapas = [(nombre, _estado_etapa(items, pasos)) for nombre, pasos in ETAPAS]
    etapas.append(("Generación de los archivos finales", "completado"))

    mensaje = EmailMessage()
    mensaje["Subject"] = (
        f"Sire · Procesamiento terminado: {len(envio['rucs'])} "
        f"{'empresa' if len(envio['rucs']) == 1 else 'empresas'}, "
        f"{len(items)} {'periodo' if len(items) == 1 else 'periodos'}"
    )
    mensaje["From"] = settings.SMTP_REMITENTE or settings.SMTP_USUARIO or ""
    mensaje["To"] = envio["correo"]

    if adjunto:
        entrega = "Adjuntamos el ZIP con los reportes y comprobantes de cada empresa y periodo."
    elif enlace:
        entrega = (
            f"El ZIP pesa más de lo que admite el correo; descárgalo aquí (válido "
            f"{settings.DESCARGA_ENLACE_DIAS} días): {enlace}"
        )
    else:
        entrega = "El ZIP pesa más de lo que admite el correo; descárgalo desde el panel de Sire."

    texto = [
        "El procesamiento que pediste en Sire ha terminado.",
        "",
        *[f"- {nombre}: {estado}" for nombre, estado in etapas],
        "",
        *[
            f"- {nombres[i['ruc']]} ({i['ruc']}) · {i['periodo'][4:]}/{i['periodo'][:4]}: "
            f"{ETIQUETA_ITEM.get(i['estado'], i['estado'])}"
            for i in items
        ],
        "",
        entrega,
    ]
    mensaje.set_content("\n".join(texto))

    filas = "".join(
        f"<tr><td>{escape(nombres[i['ruc']])}</td><td>{i['ruc']}</td>"
        f"<td>{i['periodo'][4:]}/{i['periodo'][:4]}</td>"
        f"<td>{escape(ETIQUETA_ITEM.get(i['estado'], i['estado']))}</td></tr>"
        for i in items
    )
    lista_etapas = "".join(
        f"<li>{escape(nombre)}: <strong>{escape(estado)}</strong></li>" for nombre, estado in etapas
    )
    entrega_html = (
        f'<a href="{escape(enlace)}">Descargar el ZIP</a> (válido '
        f"{settings.DESCARGA_ENLACE_DIAS} días)."
        if enlace and not adjunto
        else escape(entrega)
    )
    mensaje.add_alternative(
        "<p>El procesamiento que pediste en Sire ha terminado.</p>"
        f"<ul>{lista_etapas}</ul>"
        '<table cellpadding="6" style="border-collapse:collapse" border="1">'
        "<tr><th>Empresa</th><th>RUC</th><th>Periodo</th><th>Estado</th></tr>"
        f"{filas}</table><p>{entrega_html}</p>",
        subtype="html",
    )
    if adjunto:
        mensaje.add_attachment(
            adjunto.read_bytes(), maintype="application", subtype="zip", filename=adjunto.name
        )
    return mensaje


def _enviar(mensaje: EmailMessage) -> None:
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60) as smtp:
        smtp.starttls()
        if settings.SMTP_USUARIO:
            smtp.login(settings.SMTP_USUARIO, settings.SMTP_PASSWORD or "")
        smtp.send_message(mensaje)


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


def _enlace(solicitud_id: str, archivo: str) -> str | None:
    if not settings.APP_URL_PUBLICA:
        return None
    token = crear_token_descarga(solicitud_id, archivo)
    base = settings.APP_URL_PUBLICA.rstrip("/")
    return f"{base}{settings.API_V1_PREFIX}/descargas/{token}"


async def enviar_solicitud(db, job: Job, reportar) -> dict[str, Any]:
    """Manejador de la cola para `envio_correo`."""
    solicitud_id = job.solicitud_id or ""
    solicitud = await repo_solicitudes.obtener(db, solicitud_id)
    if not solicitud:
        raise ErrorPermanente("La solicitud ya no existe")

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
        if not permitido(envio["correo"]):
            cambios = {
                "estado": EstadoEnvio.BLOQUEADO.value,
                "error": "Destinatario fuera de CORREO_DESTINATARIOS_PERMITIDOS en este entorno",
            }
        elif not smtp_configurado():
            cambios = {
                "estado": EstadoEnvio.FALLIDO.value,
                "definitivo": True,
                "error": "El correo no está configurado (SMTP_HOST vacío)",
            }
        else:
            cambios = await _enviar_uno(db, solicitud, envio)
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


async def _enviar_uno(db, solicitud: dict[str, Any], envio: dict[str, Any]) -> dict[str, Any]:
    intentos = envio.get("intentos", 0) + 1
    try:
        zip_ = await _zip_para(db, solicitud, envio)
        limite = settings.CORREO_MAX_ADJUNTO_MB * 1024 * 1024
        adjunto = zip_ if zip_.stat().st_size <= limite else None
        enlace = None if adjunto else _enlace(str(solicitud["_id"]), zip_.name)
        mensaje = construir(solicitud, envio, adjunto=adjunto, enlace=enlace)
        await asyncio.to_thread(_enviar, mensaje)
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP rechazó el usuario o la contraseña: %s", exc.smtp_code)
        return {
            "estado": EstadoEnvio.FALLIDO.value,
            "definitivo": True,
            "intentos": intentos,
            "error": "El servidor de correo rechazó el usuario o la contraseña (SMTP)",
        }
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused) as exc:
        return {
            "estado": EstadoEnvio.FALLIDO.value,
            "definitivo": True,
            "intentos": intentos,
            "error": f"El servidor de correo rechazó la dirección: {exc}",
        }
    except Exception as exc:
        logger.warning("No se pudo enviar el correo a %s: %s", envio["correo"], exc)
        return {"estado": EstadoEnvio.FALLIDO.value, "intentos": intentos, "error": str(exc)[:500]}
    logger.info("Correo enviado a %s (%s)", envio["correo"], "adjunto" if adjunto else "enlace")
    return {
        "estado": EstadoEnvio.ENVIADO.value,
        "modo": (ModoEnvio.ADJUNTO if adjunto else ModoEnvio.ENLACE).value,
        "intentos": intentos,
        "error": None,
        "enviado_en": datetime.now(UTC),
    }
