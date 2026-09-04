import asyncio
import io
import logging
import re
import tempfile
import zipfile
from collections.abc import Callable
from contextlib import ExitStack
from datetime import date, datetime
from functools import partial
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.core.config import settings
from app.core.encryption import decrypt_password
from app.domain.comprobante import Libro, normalizar_tipo_cp
from app.services.sunat import cpe_xml

load_dotenv()

logger = logging.getLogger(__name__)

URL_MENU = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm"
URL_SEE_SOL = "https://ww1.sunat.gob.pe/ol-ti-itconscpemype/consultar.do"

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

# El rechazo del portal en el login es casi siempre transitorio: se reprodujo
# un intento fallido que, relanzado segundos despues, entro cuatro veces
# seguidas sin tocar nada. Tres intentos cubren lo observado sin acercarse al
# bloqueo del usuario, que SOL cuenta por credenciales rechazadas y esas no se
# reintentan (ver `_login_con_reintentos`).
INTENTOS_LOGIN = 3
ESPERA_REINTENTO_LOGIN_MS = 4000

# Lo que `_verificar_sesion` espera a que aparezca el menu. El mensaje de error
# lo cita, asi que va en una constante para que no se desincronicen.
TIMEOUT_MENU_MS = 20000

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

# Dentro del popup del comprobante, lo que descarga o imprime el documento. Es
# deliberadamente amplio: el portal usa un control distinto según la bandeja, y
# fallar aquí sólo cuesta caer a renderizar el popup.
SEL_PDF = (
    "a[href$='.pdf'], a[onclick*='pdf'], a[onclick*='Pdf'], a[onclick*='PDF'], "
    "a:has(img[src*='pdf']), a:has(img[src*='impresora']), "
    "a[title*='PDF'], a[title*='Imprimir'], button:has-text('PDF'), "
    "input[value*='PDF'], img[title*='PDF'], img[alt*='PDF']"
)


class SesionSolError(Exception):
    """El portal no dejó abrir (o mantener) la sesión SOL.

    Se distingue del resto de fallos porque no tiene arreglo reintentando: sin
    sesión no hay nada que raspar, y el trabajo tiene que terminar en `fallido`
    en vez de en `completado` con cero detalles.
    """


class CredencialesSolError(SesionSolError):
    """SUNAT dijo de forma explicita que el usuario o la clave estan mal.

    Se separa del resto de fallos de sesion porque es el unico que no se debe
    reintentar: ademas de inutil, SOL bloquea el usuario tras varios intentos
    fallidos, y un reintento automatico convertiria una clave mal guardada en
    una cuenta bloqueada.
    """


class ComprobanteNoEncontrado(Exception):
    """La búsqueda no devolvió resultados.

    No es un fallo del portal: reintentarlo devuelve lo mismo. Separarlo del
    resto evita gastar una segunda ronda de timeout en cada comprobante que
    SUNAT no tiene en la bandeja consultada.
    """


class CriterioRechazado(Exception):
    """El formulario rechazó un criterio, así que la búsqueda no se ejecutó.

    Cada bandeja valida el formato de sus criterios: la serie de `FE Recibidas`
    sólo acepta `F###` y la de `BVE Emitidas - OSE` sólo `B###`. Con un campo
    inválido el botón Buscar no envía nada y la página se queda igual, sin
    tabla de resultados y sin mensaje.

    Se distingue de `ComprobanteNoEncontrado` porque son cosas opuestas y antes
    se confundían: sin este aviso, una serie que el portal no admite —las `E001`
    y `EB01` de algunos contribuyentes— llegaba al log como «SUNAT no lo tiene
    en <bandeja>», idéntico a un comprobante que de verdad no está. Con eso, un
    libro de ventas entero sin extraer parecía un problema de datos de SUNAT.
    """

    def __init__(self, serie_numero: str, bandeja_usada: str, criterios: list[str]) -> None:
        self.serie_numero = serie_numero
        self.bandeja_usada = bandeja_usada
        self.criterios = criterios
        super().__init__(
            f"la bandeja {bandeja_usada} no admite " + ", ".join(criterios)
        )


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

    # El envio no puede quedar en silencio. Si `login()` ya no existe y tampoco
    # hay boton, el formulario se queda como estaba y el unico sintoma llega
    # 20 s despues como "SUNAT devolvio el formulario de login", que apunta a
    # las credenciales. Guardar el motivo es lo que separa los dos casos.
    fallo_envio: Exception | None = None
    try:
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            login_frame.evaluate("login()")
    except Exception as sin_navegacion:
        fallo_envio = sin_navegacion
        try:
            submit = login_frame.locator("button[type='submit']").first
            if submit.count() > 0:
                submit.click()
            else:
                login_frame.evaluate("login()")
            fallo_envio = None
        except Exception as sin_envio:
            fallo_envio = sin_envio
            logger.info("No se pudo enviar el formulario de login: %s", sin_envio)

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
                    raise CredencialesSolError(
                        f"Credenciales SOL incorrectas: {error_text.strip()}"
                    )
        except SesionSolError:
            raise
        except Exception:
            continue

    body_text = page.locator("body").text_content() or ""
    if "Usuario o Clave Incorrectos" in body_text or "el RUC es incorrecto" in body_text.lower():
        raise CredencialesSolError(
            "Credenciales SOL incorrectas (detectado por texto en página)"
        )

    if "api-seguridad.sunat.gob.pe" in page.url:
        page.goto(URL_MENU, wait_until="domcontentloaded", timeout=30000)

    _verificar_sesion(page, fallo_envio)


def _verificar_sesion(page, fallo_envio: Exception | None = None) -> None:
    """Confirma que el login dejó abierto el menú de SOL.

    El portal puede devolver el formulario sin dar ningún mensaje de error, así
    que los controles de arriba no lo detectan. Sin esta verificación el
    scraping seguía contra una página anónima donde `ejecuta` no existe: la
    llamada quedaba en nada y cada comprobante agotaba los 15 s de timeout del
    iframe, terminando el job en `completado` con cero detalles.
    """
    try:
        page.wait_for_function(_JS_MENU_LISTO, timeout=TIMEOUT_MENU_MS)
        return
    except Exception:
        pass

    if page.locator("#txtRuc, input[name='ruc']").count() > 0:
        # El mensaje no puede achacarlo a las credenciales: cuando de verdad
        # están mal, SUNAT lo dice y eso ya se detectó antes en `_hacer_login`.
        # Llegar hasta aquí es, por lo medido, un rechazo transitorio.
        motivo = f" El envío del formulario había fallado: {fallo_envio}." if fallo_envio else ""
        raise SesionSolError(
            "SUNAT devolvió el formulario de login y no confirmó el menú en "
            f"{TIMEOUT_MENU_MS // 1000} s.{motivo} Suele ser transitorio; si se "
            "repite en todos los intentos, revisa el RUC, el usuario y la clave SOL"
        )
    raise SesionSolError(f"No se pudo abrir el menú de SOL tras el login (url={page.url})")


def _guardar_evidencia_login(page, log, intento: int) -> None:
    """Deja en `logs/` con qué se quedó el navegador cuando el login falló.

    Sin esto un rechazo no deja nada que mirar: el navegador se cierra con el
    job y el mensaje de la excepción es idéntico si SUNAT devolvió el
    formulario porque el envío no llegó a salir, porque la sesión anterior
    seguía viva o porque las credenciales están mal. Distinguirlos después sólo
    es posible con lo que se capture aquí.

    No lanza nunca: perder la evidencia no puede tapar el fallo que la motivó.
    """
    datos = [f"url={page.url}"]
    for expresion, etiqueta in (
        ("typeof login", "typeof_login"),
        ("typeof ejecuta", "typeof_ejecuta"),
    ):
        try:
            datos.append(f"{etiqueta}={page.evaluate(expresion)}")
        except Exception:
            datos.append(f"{etiqueta}=?")
    try:
        # El cuerpo de la página de login no contiene la clave (va en un input),
        # así que es seguro dejarlo en el log.
        cuerpo = " ".join((page.locator("body").text_content() or "").split())
        datos.append(f"body={cuerpo[:300]!r}")
    except Exception:
        pass
    try:
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta = _ruta_log(f"login_falla_{marca}_intento{intento}.png")
        page.screenshot(path=ruta, full_page=True)
        datos.append(f"captura={ruta}")
    except Exception as sin_captura:
        datos.append(f"captura=no se pudo ({sin_captura})")
    log("Evidencia del login fallido: " + " ".join(datos))


def _login_con_reintentos(page, ruc: str, usuario: str, password: str, log) -> None:
    """Login SOL, reintentando los rechazos transitorios del portal.

    SUNAT devuelve el formulario de vez en cuando aunque las credenciales sean
    correctas —se reprodujo entrando justo después de cerrar otra sesión que
    había usado el módulo de consulta— y el intento siguiente entra sin cambiar
    nada. Antes eso costaba el trabajo entero: `SesionSolError` sube hasta el
    job y lo deja en `fallido`, así que un tropiezo de cuatro segundos se
    llevaba la extracción completa de un periodo.

    Las credenciales rechazadas de forma explícita no se reintentan: SOL
    bloquea el usuario tras varios intentos fallidos.
    """
    for intento in range(1, INTENTOS_LOGIN + 1):
        try:
            _hacer_login(page, ruc, usuario, password)
            if intento > 1:
                log(f"Login conseguido en el intento {intento} de {INTENTOS_LOGIN}")
            return
        except CredencialesSolError:
            raise
        except SesionSolError as rechazo:
            _guardar_evidencia_login(page, log, intento)
            if intento == INTENTOS_LOGIN:
                raise
            log(
                f"Login rechazado (intento {intento} de {INTENTOS_LOGIN}): {rechazo}. "
                f"Reintentando en {ESPERA_REINTENTO_LOGIN_MS // 1000} s"
            )
            page.wait_for_timeout(ESPERA_REINTENTO_LOGIN_MS)


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


_JS_DESCARGAR_FACTURA = """(args) => {
    let form = document.querySelector("form[name='formArchivo'], form#formArchivo, form[action*='descargarFactura']");
    if (!form) {
        form = document.createElement('form');
        form.name = 'formArchivo';
        form.method = 'POST';
        form.action = 'consultar.do?action=descargarFactura';
        document.body.appendChild(form);
    }
    function setField(name, val) {
        let input = form.querySelector(`input[name='${name}']`);
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            form.appendChild(input);
        }
        input.value = val;
    }
    setField('ruc', args.ruc);
    setField('tipo', args.tipo);
    setField('serie', args.serie);
    setField('numero', args.numero);
    form.submit();
    return true;
}"""

_JS_DESCARGAR_PDF = """(args) => {
    let form = document.querySelector("form[name='formArchivoComprobantePdf'], form#formArchivoComprobantePdf, form[action*='descargarComprobanteEnPdf']");
    if (!form) {
        form = document.createElement('form');
        form.name = 'formArchivoComprobantePdf';
        form.method = 'POST';
        form.action = 'consultar.do?action=descargarComprobanteEnPdf';
        document.body.appendChild(form);
    }
    function setField(name, val) {
        let input = form.querySelector(`input[name='${name}']`);
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            form.appendChild(input);
        }
        input.value = val;
    }
    setField('ruc', args.ruc);
    setField('tipo', args.tipo);
    setField('serie', args.serie);
    setField('numero', args.numero);
    form.submit();
    return true;
}"""


def _abrir_modulo_see_sol(page, iframe, timeout_ms: int) -> None:
    """Deja cargado el módulo de consulta SEE-SOL en el iframe principal."""
    page.evaluate(
        f"""() => {{
            const iframe = document.getElementById('iframeApplication');
            if (iframe) {{
                iframe.src = '{URL_SEE_SOL}';
            }}
        }}"""
    )
    try:
        page.wait_for_timeout(500)
        iframe.locator("body").wait_for(state="attached", timeout=timeout_ms)
    except Exception:
        pass


def _es_serie_sol(serie: str) -> bool:
    """True si la serie corresponde al Sistema de Emisión Electrónica SOL (SEE-SOL).

    En SUNAT, las series de SEE-SOL comienzan con 'E' (E### en facturas, EB## en boletas,
    EC## en notas de crédito, ED## en notas de débito). Las de SEE-Contribuyente/OSE
    comienzan con 'F' o 'B'.
    """
    return (serie or "").strip().upper().startswith("E")


def _extraer_xml_de_zip(contenido: bytes) -> bytes:
    """Extrae el archivo XML contenido dentro de un ZIP descargado de SUNAT."""
    if not contenido:
        raise ValueError("El contenido a desempaquetar está vacío")
    if contenido.startswith(b"<?xml") or contenido.startswith(b"<"):
        return contenido
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            for nombre in z.namelist():
                if nombre.lower().endswith(".xml"):
                    return z.read(nombre)
    except zipfile.BadZipFile as e:
        raise ValueError(f"El archivo descargado no es un ZIP válido: {e}") from e
    raise ValueError("El archivo ZIP de SUNAT no contiene ningún archivo .xml")


def _ruc_emisor(fac: dict, libro: Libro, ruc_empresa: str) -> str:
    """RUC del emisor del comprobante.

    En compras el emisor es la contraparte (proveedor). En ventas es la propia empresa.
    """
    if libro is Libro.COMPRAS:
        return str(fac.get("documento_contraparte") or "").strip()
    return str(ruc_empresa).strip()


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


def _criterios_rechazados(iframe, escritos: list[tuple[str, str, str]]) -> list[str]:
    """Criterios que el formulario marcó como inválidos al escribirlos.

    Dojo pone `aria-invalid="true"` en el campo y bloquea el envío, así que
    mirarlo antes de pulsar Buscar es lo único que separa «el portal no admite
    este criterio» de «el comprobante no está». Sin esto lo segundo se decía de
    lo primero y no había forma de notarlo desde el log.

    Sólo se revisan los campos en los que se escribió algo: un criterio que se
    deja vacío a propósito —el RUC del receptor en las boletas a DNI— también
    aparece como inválido, y eso no impide la búsqueda.
    """
    rechazados = []
    for selector, nombre, valor in escritos:
        if not valor:
            continue
        try:
            campo = iframe.locator(selector).first
            if campo.count() == 0:
                continue
            if campo.get_attribute("aria-invalid") == "true":
                rechazados.append(f"{nombre}={valor!r}")
        except Exception:
            # Que no se pueda leer la validación no puede impedir la búsqueda:
            # en el peor caso se sigue como antes y el portal decide.
            continue
    return rechazados


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


def _buscar(
    iframe,
    fac: dict,
    libro: Libro,
    timeout_busqueda_ms: int,
):
    """Rellena el formulario de consulta y devuelve el enlace «Visualizar».

    Se separó de `_consultar_uno` porque la descarga del PDF necesita
    exactamente los mismos pasos: elegir bandeja, escribir los criterios y
    buscar. Duplicarlos garantizaba que las dos copias divergieran en cuanto el
    portal cambiara un `id`.

    Lanza `ComprobanteNoEncontrado` si la búsqueda no devuelve resultados.
    """
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

    escritos = [
        (SEL_RUC, "el RUC", _criterio_ruc(fac, libro)),
        (SEL_SERIE, "la serie", serie),
        (SEL_NUMERO, "el número", correlativo),
    ]
    if fecha_emision_str:
        escritos.append((SEL_FEC_DESDE, "la fecha desde", fecha_emision_str))
        escritos.append((SEL_FEC_HASTA, "la fecha hasta", fecha_emision_str))

    for selector, _nombre, valor in escritos:
        _llenar(iframe.locator(selector).first, valor)

    # Pulsar Buscar con un criterio inválido no hace nada, y la espera del
    # enlace «Visualizar» de abajo acabaría contándolo como comprobante
    # ausente. Preguntarlo aquí cuesta una lectura de atributo.
    rechazados = _criterios_rechazados(iframe, escritos)
    if rechazados:
        raise CriterioRechazado(serie_num, tipo_consulta, rechazados)

    iframe.locator(SEL_BUSCAR).first.click(force=True)

    btn_visualizar = iframe.locator(SEL_VISUALIZAR).first
    # Cuando el comprobante existe, el enlace aparece en menos de un segundo.
    # Esperar aquí el timeout general sólo alargaba los que SUNAT no tiene.
    try:
        btn_visualizar.wait_for(state="attached", timeout=timeout_busqueda_ms)
    except Exception as sin_resultados:
        raise ComprobanteNoEncontrado(serie_num) from sin_resultados

    return btn_visualizar


def _capturar_pdf(popup, context, timeout_ms: int, log, serie_num: str, headless: bool):
    """Bytes del PDF del comprobante, o `None` si no se pudo obtener.

    El portal no es consistente en cómo entrega el documento, así que se
    intentan tres vías en orden de fidelidad. Un PDF que no se puede capturar
    devuelve `None` a propósito: perder un respaldo no justifica tumbar la
    descarga de los otros noventa y nueve.
    """
    # 1. El popup ya es el propio PDF. Se pide por el contexto del navegador
    #    para reutilizar la sesión SOL: una petición desde fuera devolvería el
    #    formulario de login.
    url = popup.url or ""
    if url.lower().split("?")[0].endswith(".pdf"):
        try:
            respuesta = context.request.get(url, timeout=timeout_ms)
            if respuesta.ok:
                log(f"{serie_num}: PDF tomado directamente del popup")
                return respuesta.body()
            log(f"{serie_num}: el popup es un PDF pero respondió {respuesta.status}")
        except Exception as fallo:
            log(f"{serie_num}: no se pudo descargar el PDF del popup: {fallo}")

    # 2. Un botón de impresión o de PDF dentro del popup.
    try:
        enlace = popup.locator(SEL_PDF).first
        if enlace.count() > 0:
            with popup.expect_download(timeout=timeout_ms) as descarga:
                enlace.click()
            ruta = descarga.value.path()
            if ruta:
                # Hay que leerlo ahora: el archivo vive en el directorio
                # temporal de Playwright y desaparece al cerrar el navegador.
                contenido = Path(ruta).read_bytes()
                log(f"{serie_num}: PDF descargado desde el botón del popup")
                return contenido
    except Exception as fallo:
        log(f"{serie_num}: no hubo descarga desde el popup: {fallo}")

    # 3. Renderizar la página. `Page.pdf()` sólo existe en Chromium headless,
    #    así que en modo con ventana esta vía no está disponible.
    if not headless:
        log(f"{serie_num}: sin PDF (renderizar exige modo headless)")
        return None
    try:
        contenido = popup.pdf(print_background=True)
        log(f"{serie_num}: PDF generado renderizando el popup")
        return contenido
    except Exception as fallo:
        log(f"{serie_num}: no se pudo renderizar el popup a PDF: {fallo}")
    return None


def _consultar_uno(
    page,
    context,
    iframe,
    fac: dict,
    libro: Libro,
    timeout_ms: int,
    log,
    timeout_busqueda_ms: int = 8000,
    descargar_pdf: bool = False,
    headless: bool = True,
    timeout_pdf_ms: int | None = None,
) -> tuple[list[dict], bytes | None]:
    """Líneas del comprobante y, si se pidió, su PDF. Lanza si algo falla.

    El PDF se captura aquí y no en una segunda pasada porque llegar a este
    punto ya costó login, bandeja, búsqueda y apertura del popup: repetirlo
    duplicaría la duración del trabajo y, al ser la sesión SOL única por
    usuario, las dos pasadas se pelearían por ella.
    """
    serie_num = fac.get("serie_numero", "")

    btn_visualizar = _buscar(iframe, fac, libro, timeout_busqueda_ms)

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

        detalles = _parsear_filas(popup.evaluate(_JS_LEER_TABLA))

        pdf = None
        if descargar_pdf:
            pdf = _capturar_pdf(
                popup,
                context,
                timeout_pdf_ms or settings.SUNAT_PDF_TIMEOUT_MS,
                log,
                serie_num,
                headless,
            )

        return detalles, pdf
    finally:
        # Sin esto un fallo a media lectura deja la pestaña abierta y las va
        # acumulando durante todo el job.
        try:
            popup.close()
        except Exception:
            pass



def _consultar_uno_see_sol(
    page,
    context,
    iframe,
    fac: dict,
    libro: Libro,
    ruc_empresa: str,
    timeout_ms: int,
    log,
    descargar_pdf: bool = False,
) -> tuple[list[dict], bytes | None, bytes | None]:
    """Descarga el XML y PDF de un comprobante emitido por SEE-SOL (series E/EB).

    Devuelve (detalles, pdf_bytes, xml_bytes). Lanza ComprobanteNoEncontrado si
    SUNAT no devuelve el archivo o devuelve una página de error HTML.
    """
    serie_num = fac.get("serie_numero", "")
    ruc_em = _ruc_emisor(fac, libro, ruc_empresa)
    tipo = normalizar_tipo_cp(fac.get("tipo_cp"))
    serie = str(fac.get("serie", "")).strip()
    numero_crudo = fac.get("numero", "")
    try:
        numero = str(int(numero_crudo))
    except (TypeError, ValueError):
        numero = str(numero_crudo).strip()

    args = {
        "ruc": ruc_em,
        "tipo": tipo,
        "serie": serie,
        "numero": numero,
    }

    log(f"Consultando SEE-SOL para {serie_num} (emisor={ruc_em} tipo={tipo} serie={serie} num={numero})")

    # 1. Descarga del XML (empaquetado en ZIP por SUNAT)
    xml_bytes = None
    detalles = []
    try:
        with context.expect_download(timeout=timeout_ms) as descarga_info:
            iframe.locator("body").evaluate(_JS_DESCARGAR_FACTURA, args)
        descarga = descarga_info.value
        contenido_zip = Path(descarga.path()).read_bytes()

        # Si SUNAT responde con un HTML de error (p.ej. 404 o sesión expirada)
        if contenido_zip.strip().startswith(b"<!DOCTYPE") or contenido_zip.strip().startswith(b"<html"):
            log(f"{serie_num}: SUNAT devolvió HTML en vez de ZIP para el XML")
            raise ComprobanteNoEncontrado(serie_num)

        xml_bytes = _extraer_xml_de_zip(contenido_zip)
        detalles = cpe_xml.a_detalle(xml_bytes)
        log(f"{serie_num}: XML descargado y mapeado ({len(detalles)} items)")
    except ComprobanteNoEncontrado:
        raise
    except Exception as e:
        log(f"{serie_num}: no se pudo obtener XML de SEE-SOL: {e}")
        raise ComprobanteNoEncontrado(serie_num) from e

    # 2. Descarga del PDF oficial si fue solicitado
    pdf_bytes = None
    if descargar_pdf:
        try:
            with context.expect_download(timeout=timeout_ms) as descarga_pdf_info:
                iframe.locator("body").evaluate(_JS_DESCARGAR_PDF, args)
            descarga_pdf = descarga_pdf_info.value
            contenido_pdf = Path(descarga_pdf.path()).read_bytes()
            if contenido_pdf.startswith(b"%PDF-"):
                pdf_bytes = contenido_pdf
                log(f"{serie_num}: PDF oficial descargado de SEE-SOL ({len(pdf_bytes)} bytes)")
            else:
                log(f"{serie_num}: el archivo descargado de SEE-SOL no es un PDF válido")
        except Exception as e:
            log(f"{serie_num}: no se pudo descargar PDF de SEE-SOL: {e}")

    return detalles, pdf_bytes, xml_bytes


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
    descargar_pdf: bool = False,
    al_descargar: Callable[[str, bytes], None] | None = None,
    timeout_pdf_ms: int | None = None,
    al_descargar_xml: Callable[[str, bytes], None] | None = None,
) -> dict:
    """`progreso(hechos, serie_numero)` se llama al empezar cada comprobante.

    `al_extraer(serie_numero, detalles)` se llama en cuanto cada comprobante
    termina bien. Guardar sobre la marcha es lo que evita que un tropiezo a
    mitad de la lista se lleve por delante todo lo ya recorrido.

    Con `descargar_pdf` se captura además el PDF de cada comprobante y se
    entrega por `al_descargar(serie_numero, contenido)`. Va apagado por defecto
    para que el camino de la extracción de detalle no cambie de coste.
    """
    # `print` no llegaba a logs/automat_api.log (ese handler sólo recoge el
    # módulo `logging`), así que el rastro por comprobante se perdía justo
    # cuando hacía falta para saber si un job se quedó colgado.
    def log(msg: str) -> None:
        logger.info("%s", msg)

    browser = None
    resultados = {}

    with sync_playwright() as p, ExitStack() as recursos:
        try:
            log(
                f"Iniciando navegador scraping detalles. "
                f"libro={libro.value} headed={headed} pdf={descargar_pdf}"
            )
            opciones = {
                "headless": not headed,
                "slow_mo": slow_mo_ms,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ],
            }
            if descargar_pdf:
                # Playwright borra sus descargas al cerrar el navegador, pero
                # sólo si cierra bien. Con un directorio propio la limpieza la
                # garantiza el `ExitStack` incluso si el proceso se va por un
                # camino de error.
                opciones["downloads_path"] = recursos.enter_context(
                    tempfile.TemporaryDirectory(prefix="sunat_pdf_")
                )

            browser = p.chromium.launch(**opciones)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                # Explícito a propósito: el default de Playwright ya es `True`,
                # pero dejarlo implícito hace que la captura del PDF dependa de
                # la versión de la librería.
                accept_downloads=True,
            )
            page = context.new_page()

            # `_hacer_login` ya deja confirmado que el menú está arriba, así que
            # aquí sobran los 3 s de cortesía que había antes y después.
            _login_con_reintentos(page, ruc, usuario, password, log)
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
                        if _es_serie_sol(fac.get("serie", "")):
                            _abrir_modulo_see_sol(page, iframe, timeout_ms)
                            detalles, pdf, xml = _consultar_uno_see_sol(
                                page,
                                context,
                                iframe,
                                fac,
                                libro,
                                ruc_empresa=ruc,
                                timeout_ms=timeout_ms,
                                log=log,
                                descargar_pdf=descargar_pdf,
                            )
                            if xml and al_descargar_xml:
                                al_descargar_xml(serie_num, xml)
                        else:
                            _abrir_consulta(page, iframe, timeout_ms)
                            detalles, pdf = _consultar_uno(
                                page,
                                context,
                                iframe,
                                fac,
                                libro,
                                timeout_ms,
                                log,
                                timeout_busqueda_ms,
                                descargar_pdf=descargar_pdf,
                                headless=not headed,
                                timeout_pdf_ms=timeout_pdf_ms,
                            )
                        resultados[serie_num] = detalles
                        log(f"{serie_num}: {len(detalles)} items extraidos")
                        if al_extraer:
                            al_extraer(serie_num, detalles)
                        # Un comprobante sin PDF no es un fallo del trabajo: se
                        # queda sin respaldo y se vuelve a intentar en la
                        # siguiente vuelta, porque el puntero no se guarda.
                        if pdf and al_descargar:
                            al_descargar(serie_num, pdf)
                        break
                    except CriterioRechazado as rechazo:
                        # No es un fallo transitorio: el formulario rechaza ese
                        # criterio siempre, así que reintentar sólo gastaría
                        # otra ronda de timeouts.
                        log(f"{serie_num}: no se pudo consultar, {rechazo}")
                        break
                    except ComprobanteNoEncontrado:
                        fuente = "SEE-SOL" if _es_serie_sol(fac.get("serie", "")) else bandeja(fac, libro)
                        log(
                            f"{serie_num}: SUNAT no lo tiene en "
                            f"{fuente}"
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
                                _login_con_reintentos(page, ruc, usuario, password, log)
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
    descargar_pdf: bool = False,
    al_descargar: Callable[[str, bytes], None] | None = None,
    timeout_pdf_ms: int | None = None,
    al_descargar_xml: Callable[[str, bytes], None] | None = None,
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
    if timeout_pdf_ms is None:
        timeout_pdf_ms = settings.SUNAT_PDF_TIMEOUT_MS

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
            descargar_pdf=descargar_pdf,
            al_descargar=al_descargar,
            timeout_pdf_ms=timeout_pdf_ms,
            al_descargar_xml=al_descargar_xml,
        )
    )

