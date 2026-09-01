import asyncio
import logging
import re
from collections.abc import Callable
from datetime import date, datetime
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.core.encryption import decrypt_password
from app.domain.comprobante import Libro, normalizar_tipo_cp

load_dotenv()

logger = logging.getLogger(__name__)

URL_MENU = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm"

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

# El menú de SOL expone `ejecuta()` sólo cuando la sesión está abierta. Es la
# señal más barata para distinguir "estoy dentro" de "SUNAT me devolvió al
# formulario de login", que es como fallaba antes: sin sesión, `ejecuta` no
# existe, la llamada queda en nada y cada comprobante se comía los 15 s de
# timeout del iframe hasta terminar el job con cero detalles.
_JS_MENU_LISTO = (
    "typeof ejecuta === 'function'"
    " || !!document.querySelector('#divMenu, #nivel1, #btnEmpresas, #iframeApplication')"
)


# Los ids del formulario llevan un punto literal, que en CSS va escapado.
SEL_TIPO_CONSULTA = "input#criterio\\.tipoConsulta"
SEL_RUC = "input#criterio\\.ruc"
SEL_SERIE = "input#criterio\\.serie"
SEL_NUMERO = "input#criterio\\.numero"
SEL_FEC_DESDE = "input#criterio\\.fecDesde"
SEL_FEC_HASTA = "input#criterio\\.fecHasta"
SEL_BUSCAR = (
    "#criterio\\.btnContinuar, #btnBuscar, "
    "button:has-text('Buscar'), input[value='Buscar']"
)
# El combo "Tipo de consulta" decide en qué bandeja busca el portal, y el
# portal separa una bandeja **por tipo de documento**, no una por libro. Las
# opciones reales del combo son:
#
#   FE Emitidas · FE Recibidas · NC Emitidas · NC Recibidas · ND Emitidas
#   ND Recibidas · BVE Emitidas - OSE · NC-BVE Emitidas - OSE
#   ND-BVE Emitidas - OSE
#
# Elegirla sólo por el libro daba "FE Emitidas" para todas las ventas, y el
# registro de ventas es casi todo boletas: buscarlas entre las facturas no
# encuentra nada. Es el `tipo_cp` el que manda.
TIPO_FACTURA = "01"
TIPO_BOLETA = "03"
TIPO_NOTA_CREDITO = "07"
TIPO_NOTA_DEBITO = "08"

BANDEJAS = {
    Libro.COMPRAS: {
        TIPO_FACTURA: "FE Recibidas",
        TIPO_NOTA_CREDITO: "NC Recibidas",
        TIPO_NOTA_DEBITO: "ND Recibidas",
    },
    Libro.VENTAS: {
        TIPO_FACTURA: "FE Emitidas",
        TIPO_BOLETA: "BVE Emitidas - OSE",
        TIPO_NOTA_CREDITO: "NC Emitidas",
        TIPO_NOTA_DEBITO: "ND Emitidas",
    },
}

# Una nota que corrige una boleta va en su propia bandeja. No se deduce del
# `tipo_cp` de la nota —es 07 u 08 igual que cualquier otra—, sino del tipo del
# documento que modifica, que el RVIE manda en `documentoMod` y el mapeo
# guarda en `extra.documentos_modificados`.
BANDEJAS_SOBRE_BOLETA = {
    TIPO_NOTA_CREDITO: "NC-BVE Emitidas - OSE",
    TIPO_NOTA_DEBITO: "ND-BVE Emitidas - OSE",
}

# Con un tipo que no está en la tabla se prueba la bandeja de facturas, que es
# la que cubre el grueso de cada libro.
BANDEJA_POR_DEFECTO = {Libro.COMPRAS: "FE Recibidas", Libro.VENTAS: "FE Emitidas"}

# Techo corto para escribir un criterio. En las bandejas de emitidas algunos
# campos llegan deshabilitados, y `fill` espera a que sean editables: con el
# timeout general eso costaba medio minuto por comprobante antes de rendirse.
TIMEOUT_CRITERIO_MS = 5000

SEL_VISUALIZAR = (
    "a:has(img[src*='viewdoc.gif']), a[onclick*='consultaFactura.view'], "
    "a[title*='Visualizar'], button[title*='Visualizar'], "
    "img[title*='Visualizar'], img[alt*='Visualizar'], "
    "a:has(img[src*='impresora']), a:has(img[src*='pdf'])"
)


class SesionSolError(Exception):
    """El portal no dejó abrir (o mantener) la sesión SOL.

    Se distingue del resto de fallos porque no tiene arreglo reintentando: sin
    sesión no hay nada que raspar, y el trabajo tiene que terminar en `fallido`
    en vez de en `completado` con cero detalles.
    """


class ComprobanteNoEncontrado(Exception):
    """La búsqueda no devolvió resultados.

    No es un fallo del portal: reintentarlo devuelve lo mismo. Separarlo del
    resto evita gastar una segunda ronda de timeout en cada comprobante que
    SUNAT no tiene en la bandeja consultada.
    """


def _ruta_log(nombre: str) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return str(LOG_DIR / nombre)


def _hacer_login(page, ruc: str, usuario: str, password: str) -> None:
    page.goto(URL_MENU, wait_until="domcontentloaded", timeout=60000)

    # Si la sesión seguía viva, SUNAT deja el menú directamente y no hay
    # formulario que rellenar. Sin esta salida, un re-login preventivo se
    # quedaba 20 s esperando un `#txtRuc` que nunca iba a aparecer y terminaba
    # matando el trabajo.
    if _menu_abierto(page):
        return

    iframes = page.frames
    login_frame = page

    ruc_found = False
    timeout_start = datetime.now()

    while not ruc_found and (datetime.now() - timeout_start).total_seconds() < 20:
        try:
            if page.locator("#txtRuc").count() > 0:
                login_frame = page
                ruc_found = True
                break
            elif page.locator("input[name='ruc']").count() > 0:
                login_frame = page
                ruc_found = True
                break
            else:
                for frame in iframes:
                    try:
                        if frame.locator("#txtRuc").count() > 0 or frame.locator("input[name='ruc']").count() > 0:
                            login_frame = frame
                            ruc_found = True
                            break
                    except Exception:
                        continue

            if not ruc_found:
                page.wait_for_timeout(500)
        except Exception:
            page.wait_for_timeout(500)

    if not ruc_found:
        page.wait_for_timeout(3000)
        if page.locator("#txtRuc").count() > 0 or page.locator("input[name='ruc']").count() > 0:
            login_frame = page
            ruc_found = True

    if not ruc_found:
        raise SesionSolError("No se encontró el formulario de login SOL después de 20 segundos")

    if login_frame.locator("#btnPorRuc").count() > 0:
        login_frame.click("#btnPorRuc")

    ruc_field = login_frame.locator("#txtRuc").first
    if ruc_field.count() == 0:
        ruc_field = login_frame.locator("input[name='ruc']").first

    usuario_field = login_frame.locator("#txtUsuario").first
    if usuario_field.count() == 0:
        usuario_field = login_frame.locator("input[name='usuario'], input[placeholder*='usuario']").first

    password_field = login_frame.locator("#txtContrasena").first
    if password_field.count() == 0:
        password_field = login_frame.locator("input[name='contrasena'], input[name='password'], input[type='password']").first

    ruc_field.fill(ruc)
    usuario_field.fill(usuario)
    password_field.fill(password)

    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            login_frame.evaluate("login()")
    except Exception:
        try:
            submit = login_frame.locator("button[type='submit']").first
            if submit.count() > 0:
                submit.click()
            else:
                login_frame.evaluate("login()")
        except Exception:
            pass

    # Antes eran 2 s a ciegas; esperar el fin de la navegación cuesta lo que
    # realmente tarde el redirect.
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass

    posibles_errores = [".msgError", ".alert-danger", "#errorMsg", ".error-message"]
    for selector in posibles_errores:
        try:
            if page.locator(selector).count() > 0:
                error_text = page.locator(selector).first.text_content() or ""
                if any(kw in error_text.lower() for kw in ["incorrecto", "inválido", "vuelva a intentar", "no se encontró", "por favor"]):
                    raise SesionSolError(f"Credenciales SOL incorrectas: {error_text.strip()}")
        except SesionSolError:
            raise
        except Exception:
            continue

    body_text = page.locator("body").text_content() or ""
    if "Usuario o Clave Incorrectos" in body_text or "el RUC es incorrecto" in body_text.lower():
        raise SesionSolError("Credenciales SOL incorrectas (detectado por texto en página)")

    if "api-seguridad.sunat.gob.pe" in page.url:
        page.goto(URL_MENU, wait_until="domcontentloaded", timeout=30000)

    _verificar_sesion(page)


def _verificar_sesion(page) -> None:
    """Confirma que el login dejó abierto el menú de SOL.

    SUNAT rechaza credenciales devolviendo el formulario, no un mensaje de
    error, así que los controles de arriba no lo detectan. Sin esta verificación
    el scraping seguía contra una página anónima donde `ejecuta` no existe: la
    llamada quedaba en nada y cada comprobante agotaba los 15 s de timeout del
    iframe, terminando el job en `completado` con cero detalles.
    """
    try:
        page.wait_for_function(_JS_MENU_LISTO, timeout=20000)
        return
    except Exception:
        pass

    if page.locator("#txtRuc, input[name='ruc']").count() > 0:
        raise SesionSolError(
            "SUNAT devolvió el formulario de login: revisa el RUC, el usuario y la clave SOL"
        )
    raise SesionSolError(f"No se pudo abrir el menú de SOL tras el login (url={page.url})")


def _hay_formulario_login(page) -> bool:
    try:
        return page.locator("#txtRuc, input[name='ruc']").count() > 0
    except Exception:
        return False


def _menu_abierto(page) -> bool:
    """La sesión sigue viva y el menú de SOL está delante."""
    try:
        return not _hay_formulario_login(page) and bool(page.evaluate(_JS_MENU_LISTO))
    except Exception:
        return False


def _es_sesion_expirada(page) -> bool:
    """Sólo cuenta como sesión caída si SUNAT nos devolvió al login.

    Antes bastaba con encontrar `#bntVolver` o las cadenas "sesi" y "expir" en
    el cuerpo, y el propio menú trae "Cerrar Sesión" y avisos de expiración: el
    heurístico daba positivo casi siempre. Un comprobante que simplemente no
    aparecía en SUNAT desencadenaba un re-login innecesario que, con la sesión
    aún viva, no encontraba formulario y tumbaba el trabajo entero.
    """
    return _hay_formulario_login(page)


def _llenar(campo, valor: str) -> None:
    """Escribe un criterio de búsqueda en un campo Dojo.

    `fill` emite el evento `input` que Dojo necesita para validar y `Tab`
    dispara el blur, así que no hace falta teclear letra por letra. Los cinco
    campos de texto costaban unos 4,8 s por comprobante entre el retardo de
    50 ms por tecla y el medio segundo de cortesía que venía detrás de cada uno.

    Un criterio vacío no se escribe: no hay nada que poner —el formulario se
    recarga entero entre comprobantes, así que no queda residuo del anterior— y
    además `fill` espera a que el campo sea *editable*. En las bandejas de
    emitidas algunos criterios llegan deshabilitados, y ahí esa espera se
    tragaba el timeout completo del paso por cada comprobante.
    """
    if not valor or campo.count() == 0:
        return
    try:
        campo.fill(valor, timeout=TIMEOUT_CRITERIO_MS)
    except Exception:
        # Un criterio que el portal no acepta se omite: serie, número y fecha
        # bastan para identificar el comprobante.
        logger.info("El portal no aceptó un criterio de búsqueda; se omite")
        return
    campo.press("Tab")


# Cabeceras y totales del comprobante. Comparten forma con las líneas de ítem,
# así que el único modo de descartarlos es mirar la descripción.
PALABRAS_EXCLUIR = {
    "cant.(a)", "u.m.", "código", "descripción", "valor unit.(b)",
    "precio unit.", "valor v.(a)*(b)", "icbper",
    "descuento", "total", "sumatoria", "importe",
    "tipo de comprobante", "número", "fecha de emisión", "moneda",
    "ruc", "razón social", "domicilio", "tipo de documento",
    "numero de documento",
}

# Orden de las columnas en la tabla de ítems del popup de SUNAT.
_COLUMNAS = (
    "cantidad",
    "unidad_medida",
    "codigo",
    "descripcion",
    "valor_unitario",
    "precio_unitario",
    "valor_venta",
    "icbper",
)


def _parsear_filas(filas: list[list[str]]) -> list[dict]:
    """Convierte las celdas crudas del popup en líneas de detalle.

    Se separa del scraping porque es la única parte con reglas de negocio y
    porque así se puede probar sin levantar un navegador. Una fila cuenta como
    ítem si trae al menos 6 celdas, la primera es un número (la cantidad) y la
    descripción no es una cabecera.
    """
    detalles = []
    for fila in filas:
        celdas = [c.strip() for c in fila]
        if len(celdas) < 6:
            continue

        try:
            float(celdas[0].replace(",", "").replace(" ", ""))
        except ValueError:
            continue

        descripcion = celdas[3]
        if any(p in descripcion.lower() for p in PALABRAS_EXCLUIR):
            continue

        detalles.append(
            {
                nombre: celdas[i] if i < len(celdas) else ""
                for i, nombre in enumerate(_COLUMNAS)
            }
        )
    return detalles


# Una sola llamada al navegador en vez de un round-trip por fila: leer la tabla
# celda a celda con `locator.nth(i)` costaba cientos de milisegundos en
# comprobantes largos.
_JS_LEER_TABLA = """() => Array.from(document.querySelectorAll('table tr'))
    .map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.textContent))
    .filter(celdas => celdas.length > 0)"""



_JS_ABRIR_CONSULTA = (
    "if(typeof ejecuta === 'function'){ ejecuta("
    "'MenuInternet.htm?action=iconExecute&code=11.9.5.1.1',false,"
    "'Consultar Factura, Boletas y Notas','#nivel1_11','11.9.5.1.1'); }"
)


def _abrir_modulo_empresas(page, log) -> None:
    try:
        tab_empresas = page.locator("#btnEmpresas, a:has-text('Empresas')").first
        if tab_empresas.count() > 0:
            tab_empresas.click()
            # `#nivel1_11` es la rama de Empresas que cuelga del menú y la que
            # `ejecuta(...)` referencia al abrir la consulta.
            try:
                page.locator("#nivel1_11").wait_for(state="attached", timeout=10000)
            except Exception:
                page.wait_for_timeout(1000)
    except Exception as e:
        log(f"Error navegando menú principal: {e}")


def _abrir_consulta(page, iframe, timeout_ms: int) -> None:
    """Deja el formulario de consulta listo dentro del iframe."""
    page.evaluate(_JS_ABRIR_CONSULTA)
    iframe.locator(SEL_TIPO_CONSULTA).wait_for(state="visible", timeout=timeout_ms)


def _modifica_una_boleta(fac: dict) -> bool:
    """Si la nota corrige una boleta y no una factura."""
    documentos = (fac.get("extra") or {}).get("documentos_modificados") or []
    return any(
        isinstance(doc, dict)
        and normalizar_tipo_cp(doc.get("codTipoCDP") or doc.get("tipo_cp")) == TIPO_BOLETA
        for doc in documentos
    )


def bandeja(fac: dict, libro: Libro) -> str:
    """Opción del combo en la que el portal tiene ese comprobante."""
    tipo = normalizar_tipo_cp(fac.get("tipo_cp"))
    if (
        libro is Libro.VENTAS
        and tipo in BANDEJAS_SOBRE_BOLETA
        and _modifica_una_boleta(fac)
    ):
        return BANDEJAS_SOBRE_BOLETA[tipo]
    return BANDEJAS[libro].get(tipo) or BANDEJA_POR_DEFECTO[libro]


def _criterio_ruc(fac: dict, libro: Libro) -> str:
    """RUC de la contraparte que acepta el formulario, o cadena vacía.

    En compras es el emisor y siempre es un RUC. En ventas es el receptor, que
    en las boletas suele ser un DNI o directamente no venir ("VARIOS
    CLIENTES"): meterlo en un campo que espera once dígitos deja la búsqueda
    sin resultados. Sin él, serie + número + fecha ya identifican de forma
    única el comprobante.
    """
    documento = fac.get("documento_contraparte", "") or ""
    if libro is Libro.VENTAS and len(documento) != 11:
        return ""
    return documento


def _consultar_uno(
    page,
    context,
    iframe,
    fac: dict,
    libro: Libro,
    timeout_ms: int,
    log,
    timeout_busqueda_ms: int = 8000,
) -> list[dict]:
    """Busca un comprobante y devuelve sus líneas. Lanza si algo falla."""
    serie_num = fac.get("serie_numero", "")
    fecha_emision = fac.get("fecha_emision")
    serie = fac.get("serie", "")
    numero = fac.get("numero", "")
    tipo_consulta = bandeja(fac, libro)

    # El portal espera dd/mm/aaaa.
    fecha_emision_str = ""
    if isinstance(fecha_emision, (datetime, date)):
        fecha_emision_str = fecha_emision.strftime("%d/%m/%Y")

    # El combo es un dijit.FilteringSelect: filtra mientras se teclea, así que
    # aquí sí hacen falta los eventos de tecla. Lo que sobra es el retardo entre
    # ellas y la espera fija a que aparezca la lista.
    combo = iframe.locator(SEL_TIPO_CONSULTA).first
    if combo.count() > 0:
        combo.click()
        combo.fill("")
        combo.press_sequentially(tipo_consulta, delay=0)

        # El rótulo tiene que casar entero: "BVE Emitidas - OSE" es subcadena
        # de "NC-BVE Emitidas - OSE" y de "ND-BVE Emitidas - OSE", así que un
        # `has-text` acabaría eligiendo la bandeja de las notas.
        opcion_popup = iframe.locator(
            "li.dijitMenuItem",
            has_text=re.compile(rf"^\s*{re.escape(tipo_consulta)}\s*$"),
        ).first
        try:
            opcion_popup.wait_for(state="visible", timeout=5000)
            opcion_popup.click()
        except Exception:
            # Sin lista desplegada queda confirmar lo tecleado.
            combo.press("ArrowDown")
            combo.press("Enter")

    # El formulario pide el correlativo sin ceros a la izquierda. Al dejar de
    # filtrar series entran números que no son puramente numéricos, y esos van
    # tal cual en vez de reventar la consulta entera.
    try:
        correlativo = str(int(numero))
    except (TypeError, ValueError):
        correlativo = str(numero)

    _llenar(iframe.locator(SEL_RUC).first, _criterio_ruc(fac, libro))
    _llenar(iframe.locator(SEL_SERIE).first, serie)
    _llenar(iframe.locator(SEL_NUMERO).first, correlativo)

    if fecha_emision_str:
        _llenar(iframe.locator(SEL_FEC_DESDE).first, fecha_emision_str)
        _llenar(iframe.locator(SEL_FEC_HASTA).first, fecha_emision_str)

    iframe.locator(SEL_BUSCAR).first.click(force=True)

    btn_visualizar = iframe.locator(SEL_VISUALIZAR).first
    # Cuando el comprobante existe, el enlace aparece en menos de un segundo.
    # Esperar aquí el timeout general sólo alargaba los que SUNAT no tiene.
    try:
        btn_visualizar.wait_for(state="attached", timeout=timeout_busqueda_ms)
    except Exception as sin_resultados:
        raise ComprobanteNoEncontrado(serie_num) from sin_resultados

    log(f"Abriendo popup para {serie_num}")
    with context.expect_page(timeout=timeout_ms) as popup_info:
        btn_visualizar.click()
    popup = popup_info.value
    try:
        popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

        # Esperar la tabla en vez de un segundo a ciegas.
        try:
            popup.locator("table tr:has(td)").first.wait_for(
                state="attached", timeout=timeout_ms
            )
        except Exception:
            log(f"{serie_num}: el popup no mostro ninguna tabla")

        return _parsear_filas(popup.evaluate(_JS_LEER_TABLA))
    finally:
        # Sin esto un fallo a media lectura deja la pestaña abierta y las va
        # acumulando durante todo el job.
        try:
            popup.close()
        except Exception:
            pass



def _scrape_detalles(
    ruc: str,
    usuario: str,
    password: str,
    facturas_a_buscar: list[dict],
    libro: Libro = Libro.COMPRAS,
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
    progreso: Callable[[int, str], None] | None = None,
    timeout_ms: int = 15000,
    al_extraer: Callable[[str, list[dict]], None] | None = None,
    timeout_busqueda_ms: int = 8000,
) -> dict:
    """`progreso(hechos, serie_numero)` se llama al empezar cada comprobante.

    `al_extraer(serie_numero, detalles)` se llama en cuanto cada comprobante
    termina bien. Guardar sobre la marcha es lo que evita que un tropiezo a
    mitad de la lista se lleve por delante todo lo ya recorrido.
    """
    # `print` no llegaba a logs/automat_api.log (ese handler sólo recoge el
    # módulo `logging`), así que el rastro por comprobante se perdía justo
    # cuando hacía falta para saber si un job se quedó colgado.
    def log(msg: str) -> None:
        logger.info("%s", msg)

    browser = None
    resultados = {}

    with sync_playwright() as p:
        try:
            log(
                f"Iniciando navegador scraping detalles. "
                f"libro={libro.value} headed={headed}"
            )
            browser = p.chromium.launch(
                headless=not headed,
                slow_mo=slow_mo_ms,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # `_hacer_login` ya deja confirmado que el menú está arriba, así que
            # aquí sobran los 3 s de cortesía que había antes y después.
            _hacer_login(page, ruc, usuario, password)
            _abrir_modulo_empresas(page, log)

            iframe = page.frame_locator("#iframeApplication")

            for hechos, fac in enumerate(facturas_a_buscar):
                serie_num = fac.get("serie_numero", "")
                if progreso:
                    progreso(hechos, serie_num)

                if not fac.get("serie") or not fac.get("numero"):
                    continue

                log(f"Buscando comprobante: {serie_num}")

                # Dos vueltas: la primera recarga el formulario y consulta; si
                # algo falla se recupera la sesión (si es lo que se rompió) y se
                # vuelve a intentar una sola vez. Antes cualquier tropiezo daba
                # el comprobante por perdido.
                for intento in (1, 2):
                    try:
                        _abrir_consulta(page, iframe, timeout_ms)
                        detalles = _consultar_uno(
                            page,
                            context,
                            iframe,
                            fac,
                            libro,
                            timeout_ms,
                            log,
                            timeout_busqueda_ms,
                        )
                        resultados[serie_num] = detalles
                        log(f"{serie_num}: {len(detalles)} items extraidos")
                        if al_extraer:
                            al_extraer(serie_num, detalles)
                        break
                    except ComprobanteNoEncontrado:
                        log(
                            f"{serie_num}: SUNAT no lo tiene en "
                            f"{bandeja(fac, libro)}"
                        )
                        break
                    except Exception as e:
                        if intento == 2:
                            log(f"Error procesando {serie_num}: {e}")
                            if debug:
                                page.screenshot(
                                    path=_ruta_log(f"error_{serie_num.replace('-', '_')}.png")
                                )
                            break

                        if _es_sesion_expirada(page):
                            log("Sesión SOL expirada: reintentando login")
                            try:
                                _hacer_login(page, ruc, usuario, password)
                                _abrir_modulo_empresas(page, log)
                            except Exception as fallo_login:
                                # Que no se pueda recuperar la sesión no puede
                                # costar los comprobantes ya recorridos: se
                                # corta la vuelta y se devuelve lo que haya.
                                log(f"No se pudo recuperar la sesión: {fallo_login}")
                                return resultados
                        else:
                            log(f"Reintentando {serie_num}: {e}")

            return resultados

        except SesionSolError:
            # Sin sesión no hay nada que devolver: que el job muera y lo diga.
            raise
        except Exception as e:
            logger.exception("Fallo general del scraping de detalle")
            log(f"Fallo general: {str(e)}")
            return resultados
        finally:
            if browser:
                browser.close()


async def obtener_detalles(
    empresa: dict,
    comprobantes: list[dict],
    libro: Libro = Libro.COMPRAS,
    debug: bool = False,
    headed: bool | None = None,
    slow_mo_ms: int = 0,
    progreso: Callable[[int, str], None] | None = None,
    timeout_ms: int | None = None,
    al_extraer: Callable[[str, list[dict]], None] | None = None,
    timeout_busqueda_ms: int | None = None,
) -> dict:
    password_cifrada = empresa.get("password")
    if not password_cifrada:
        raise ValueError("No hay contraseña SOL guardada para ejecutar el scraping")

    if headed is None:
        headed = not settings.SUNAT_SCRAPER_HEADLESS
    if timeout_ms is None:
        timeout_ms = settings.SUNAT_SCRAPER_TIMEOUT_MS
    if timeout_busqueda_ms is None:
        timeout_busqueda_ms = settings.SUNAT_TIMEOUT_BUSQUEDA_MS

    # Playwright es síncrono, así que el scraping vive en un hilo aparte.
    # `progreso` se invoca desde ahí: quien lo pase es responsable de devolver
    # el aviso a su propio loop.
    #
    # Los argumentos van por nombre a propósito. Antes iban por posición y
    # reordenar la firma no daba error: el callback de avance acababa en otro
    # parámetro y el contador se quedaba quieto sin que nada lo delatara.
    return await asyncio.to_thread(
        partial(
            _scrape_detalles,
            empresa["ruc"],
            empresa["usuario"],
            decrypt_password(password_cifrada),
            comprobantes,
            libro=libro,
            debug=debug,
            headed=headed,
            slow_mo_ms=slow_mo_ms,
            progreso=progreso,
            timeout_ms=timeout_ms,
            al_extraer=al_extraer,
            timeout_busqueda_ms=timeout_busqueda_ms,
        )
    )

