"""Consulta de NPD en el menú SOL regular, con cookies de la misma sesión."""

from __future__ import annotations

import asyncio
import calendar
import logging
import re
import time
from datetime import date
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.core.encryption import decrypt_password
from app.domain.comprobante import Libro
from app.services import almacen_pdf, scraping_sunat
from app.services.scraping_sunat import SesionSolError

logger = logging.getLogger(__name__)
BASE = "https://ww1.sunat.gob.pe/cl-ti-itnumpagdetr/consultaIndividual.htm"
MENU_NPD = "#nivel4_12_4_1_1_6"


def intervalos(periodo):
    # Este formulario admite hasta 12 meses; se consulta el mes completo una vez.
    inicio = date(int(periodo[:4]), int(periodo[4:]), 1)
    fin = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
    yield inicio.strftime("%d/%m/%Y"), fin.strftime("%d/%m/%Y")


def _formulario(context):
    for page in context.pages:
        for frame in page.frames:
            try:
                if frame.locator("#fec_ini").count():
                    return frame
            except PlaywrightError:
                continue
    return None


def _abrir(context, page, ruc, usuario, password):
    scraping_sunat._login_con_reintentos(page, ruc, usuario, password, logger.info)
    scraping_sunat._abrir_modulo_empresas(page, logger.info)
    # Se acciona el menú para que SUNAT genere el token del iframe y sus cookies.
    for selector in ("#nivel1_12", "#nivel2_12_4", "#nivel3_12_4_1", MENU_NPD):
        opcion = page.locator(selector).first
        opcion.wait_for(state="attached", timeout=15000)
        opcion.evaluate("el => el.click()")
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        frame = _formulario(context)
        if frame is not None:
            frame.locator("#fec_ini").wait_for(state="visible", timeout=15000)
            return frame
        page.wait_for_timeout(250)
    raise SesionSolError("No se abrió el formulario Consulta de NPD del menú SOL")


def _es_consulta(respuesta):
    url = urlsplit(respuesta.url)
    query = parse_qs(url.query)
    return (
        url.hostname == "ww1.sunat.gob.pe"
        and url.path == "/cl-ti-itnumpagdetr/consultaIndividual.htm"
        and query.get("action") == ["consultarPadronIndividual"]
        and respuesta.request.method == "POST"
    )


def _leer_listado(respuesta):
    if not respuesta.ok:
        raise SesionSolError(f"Consulta NPD: HTTP {respuesta.status}")
    try:
        datos = respuesta.json()
    except ValueError:
        raise SesionSolError("SUNAT no devolvió el listado JSON de NPD") from None
    if not isinstance(datos, dict) or datos.get("beanErr"):
        raise SesionSolError("SUNAT rechazó la consulta del periodo NPD")
    filas = datos.get("resultado")
    if not isinstance(filas, list):
        raise SesionSolError("SUNAT devolvió un formato inesperado de NPD")
    return filas


def _listar(frame, page, periodo):
    inicio, fin = next(intervalos(periodo))
    frame.locator("#fec_ini").fill(inicio)
    frame.locator("#fec_fin").fill(fin)
    # Hay dos btnConsultar en el HTML: se elige explícitamente el de fechas.
    with frame.page.expect_response(_es_consulta, timeout=60000) as respuesta:
        frame.locator("button[onclick='consultar(2)']").click()
    return _leer_listado(respuesta.value)


JS_DETALLE = r"""() => {
    const texto = el => (el.textContent || '').replace(/\s+/g, ' ').trim();
    const campos = {};
    document.querySelectorAll('.panel-primary .panel-body .row').forEach(row => {
        const hijos = [...row.children].filter(el => el.tagName === 'DIV');
        if (hijos.length === 3 && texto(hijos[1]) === ':') {
            campos[texto(hijos[0])] = texto(hijos[2]);
        }
    });
    const tabla = document.querySelector('#tblDepositoDetracciones');
    const columnas = tabla ? [...tabla.querySelectorAll('thead th')].map(texto) : [];
    const filas = tabla ? [...tabla.querySelectorAll('tbody tr')].map(row =>
        [...row.querySelectorAll('td')].map(texto)) : [];
    return {campos, columnas, filas, tabla: !!tabla};
}"""


def _validar_detalle(extraido, numero, ruc):
    campos = extraido.get("campos", {})
    if (
        campos.get("Número de Pago de Detracciones - NPD") != numero
        or campos.get("RUC del que generó el NPD") != ruc
        or not extraido.get("tabla")
    ):
        raise SesionSolError("El detalle devuelto no corresponde al NPD y la empresa solicitados")
    columnas = extraido["columnas"]
    filas = extraido["filas"]
    if not columnas or any(len(fila) != len(columnas) for fila in filas):
        raise SesionSolError("El detalle de depósitos NPD tiene un formato inesperado")
    return {
        "cabecera": campos,
        "depositos": [dict(zip(columnas, fila, strict=True)) for fila in filas],
    }


def _seleccionar(context, numero):
    respuesta = context.request.post(
        BASE,
        params={"action": "consultarNPD", "num_npd": numero},
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://ww1.sunat.gob.pe",
            "Referer": BASE + "?action=cargarFrmConsultaIndividualSOL",
        },
        timeout=60000,
    )
    try:
        if not respuesta.ok:
            raise SesionSolError(f"Selección NPD: HTTP {respuesta.status}")
        # Este POST puede responder vacío: el detalle se guarda en la sesión.
        contenido = respuesta.body().strip()
        if contenido:
            try:
                datos = respuesta.json()
            except ValueError:
                raise SesionSolError("La selección NPD devolvió una página inesperada") from None
            if (
                not isinstance(datos, dict)
                or datos.get("beanErr")
                or (datos.get("beanM") or {}).get("error")
            ):
                raise SesionSolError("SUNAT no pudo seleccionar el NPD solicitado")
    finally:
        respuesta.dispose()


def _detalle(context, page, numero, ruc):
    _seleccionar(context, numero)
    respuesta = page.goto(
        BASE + "?action=mostrarDetalleNDP", wait_until="domcontentloaded", timeout=60000
    )
    if respuesta is None or not respuesta.ok:
        raise SesionSolError("SUNAT no devolvió la página de detalle NPD")
    page.locator("#tblDepositoDetracciones").wait_for(state="attached", timeout=15000)
    return _validar_detalle(page.evaluate(JS_DETALLE), numero, ruc)


def _pdf(context, numero, ruc, periodo):
    respuesta = context.request.get(BASE, params={"action": "generarPDFxNPD"}, timeout=60000)
    try:
        contenido = respuesta.body()
        if not respuesta.ok or not contenido.startswith(b"%PDF-"):
            raise SesionSolError("SUNAT no devolvió el PDF del NPD seleccionado")
        destino = (
            almacen_pdf.raiz_periodo(ruc, Libro.COMPRAS, periodo).parent.parent / "npds" / periodo
        )
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / f"{numero}.pdf"
        archivo.write_bytes(contenido)
        return almacen_pdf.relativa(archivo)
    finally:
        respuesta.dispose()


def _scrape(ruc, usuario, password, periodo, progreso=None):
    def avisar(mensaje):
        if progreso:
            progreso(mensaje)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.SUNAT_SCRAPER_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        try:
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            context.set_default_timeout(settings.SUNAT_SCRAPER_TIMEOUT_MS)
            page = context.new_page()
            avisar("Iniciando sesión SOL y abriendo Consulta de NPD")
            frame = _abrir(context, page, ruc, usuario, password)
            avisar("Consultando el listado NPD del mes completo")
            filas = _listar(frame, page, periodo)
            npds = {}
            for fila in filas:
                if not isinstance(fila, dict):
                    raise SesionSolError("Fila NPD inválida")
                numero = str(fila.get("numNpd") or "")
                if not re.fullmatch(r"[0-9]{13}", numero) or str(fila.get("numRuc")) != ruc:
                    raise SesionSolError(
                        "El NPD no corresponde a la empresa o tiene un número inválido"
                    )
                npds[numero] = fila
            salida = []
            detalle_page = context.new_page()
            for indice, (numero, cabecera) in enumerate(npds.items(), 1):
                avisar(f"Obteniendo detalle y PDF del NPD {indice} de {len(npds)}")
                # La selección es estado de sesión: nunca paralelizar estos pasos.
                detalle = _detalle(context, detalle_page, numero, ruc)
                registro = {"numero": numero, "cabecera": cabecera, "detalle": detalle}
                try:
                    registro["pdf_ruta"] = _pdf(context, numero, ruc, periodo)
                except (SesionSolError, PlaywrightError, OSError):
                    registro["error_pdf"] = (
                        "SUNAT no permitió descargar el PDF; el detalle está disponible"
                    )
                salida.append(registro)
            return {"npds": salida}
        except PlaywrightError as exc:
            red = re.search(r"net::[A-Z_]+", str(exc))
            motivo = red.group(0) if red else "No se pudo completar la navegación o consulta SOL"
            raise SesionSolError(f"Consulta de NPD: {motivo}") from None
        finally:
            browser.close()


async def obtener(empresa, periodo, progreso=None):
    return await asyncio.to_thread(
        _scrape,
        empresa["ruc"],
        empresa["usuario"],
        decrypt_password(empresa["password"]),
        periodo,
        progreso,
    )
