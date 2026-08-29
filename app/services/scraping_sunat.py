import asyncio
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.core.encryption import decrypt_password

load_dotenv()

URL_MENU = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm"

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def _ruta_log(nombre: str) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return str(LOG_DIR / nombre)


def _hacer_login(page, ruc: str, usuario: str, password: str) -> None:
    page.goto(URL_MENU, wait_until="domcontentloaded", timeout=60000)

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
        raise Exception("No se encontró el formulario de login SOL después de 20 segundos")

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

    page.wait_for_timeout(2000)

    posibles_errores = [".msgError", ".alert-danger", "#errorMsg", ".error-message"]
    for selector in posibles_errores:
        try:
            if page.locator(selector).count() > 0:
                error_text = page.locator(selector).first.text_content() or ""
                if any(kw in error_text.lower() for kw in ["incorrecto", "inválido", "vuelva a intentar", "no se encontró", "por favor"]):
                    raise ValueError(f"Credenciales SOL incorrectas: {error_text.strip()}")
        except ValueError:
            raise
        except Exception:
            continue

    body_text = page.locator("body").text_content() or ""
    if "Usuario o Clave Incorrectos" in body_text or "el RUC es incorrecto" in body_text.lower():
        raise ValueError("Credenciales SOL incorrectas (detectado por texto en página)")

    if "api-seguridad.sunat.gob.pe" in page.url:
        page.goto(URL_MENU, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)


def _es_sesion_expirada(page) -> bool:
    try:
        if page.locator("#bntVolver").count() > 0:
            return True
        body = (page.text_content("body") or "").lower()
        return "sesi" in body and "expir" in body
    except Exception:
        return False


def _scrape_detalles(
    ruc: str,
    usuario: str,
    password: str,
    facturas_a_buscar: list[dict],
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
    progreso: Callable[[int, str], None] | None = None,
) -> dict:
    """`progreso(hechos, serie_numero)` se llama al empezar cada comprobante.

    Recorrer un comprobante toma más de diez segundos, así que sin este aviso el
    trabajo se pasa minutos enteros sin mover el contador y no hay forma de
    distinguirlo de uno colgado.
    """
    debug_logs = []

    def log(msg: str):
        line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
        debug_logs.append(line)
        print(line)

    browser = None
    resultados = {}

    with sync_playwright() as p:
        try:
            log(f"Iniciando navegador scraping detalles. headed={headed}")
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

            _hacer_login(page, ruc, usuario, password)
            page.wait_for_timeout(3000)

            try:
                tab_empresas = page.locator("#btnEmpresas, a:has-text('Empresas')").first
                if tab_empresas.count() > 0:
                    tab_empresas.click()
                    page.wait_for_timeout(2000)
                    
            except Exception as e:
                log(f"Error navegando menú principal: {e}")

            page.wait_for_timeout(3000)
            
            iframe = page.frame_locator("#iframeApplication")
            
            for hechos, fac in enumerate(facturas_a_buscar):
                serie_num = fac.get("serie_numero", "")
                if progreso:
                    progreso(hechos, serie_num)

                try:
                    page.evaluate("if(typeof ejecuta === 'function'){ ejecuta('MenuInternet.htm?action=iconExecute&code=11.9.5.1.1',false,'Consultar Factura, Boletas y Notas','#nivel1_11','11.9.5.1.1'); }")
                    iframe.locator("input#criterio\\.tipoConsulta").wait_for(state="visible", timeout=15000)
                    page.wait_for_timeout(500)
                except Exception as e:
                    log(f"Error cargando iframe: {e}")
                    page.screenshot(path=_ruta_log("error_iframe_timeout.png"))
                    continue
                
                ruc_emisor = fac.get("documento_contraparte", "")
                fecha_emision = fac.get("fecha_emision")
                serie = fac.get("serie", "")
                numero = fac.get("numero", "")

                if not serie or not numero:
                    continue

                log(f"Buscando comprobante: {serie_num}")

                try:
                    # El portal espera dd/mm/aaaa.
                    fecha_emision_str = ""
                    if isinstance(fecha_emision, (datetime, date)):
                        fecha_emision_str = fecha_emision.strftime("%d/%m/%Y")

                    combo = iframe.locator("input#criterio\\.tipoConsulta").first
                    if combo.count() > 0:
                        combo.click()
                        combo.fill("")
                        page.wait_for_timeout(500)
                        combo.press_sequentially("FE Recibidas", delay=100)
                        page.wait_for_timeout(1500)
                        
                        opcion_popup = iframe.locator("li.dijitMenuItem:has-text('FE Recibidas'), li.dijitMenuItem:has-text('Recibidas')").first
                        if opcion_popup.count() > 0:
                            opcion_popup.click()
                        else:
                            combo.press("ArrowDown")
                            page.wait_for_timeout(300)
                            combo.press("Enter")
                        page.wait_for_timeout(1000)

                    ruc_input = iframe.locator("input#criterio\\.ruc").first
                    if ruc_input.count() > 0:
                        ruc_input.click()
                        ruc_input.fill("")
                        ruc_input.press_sequentially(ruc_emisor, delay=50)
                        ruc_input.press("Tab")
                        page.wait_for_timeout(500)

                    serie_input = iframe.locator("input#criterio\\.serie").first
                    if serie_input.count() > 0:
                        serie_input.click()
                        serie_input.fill("")
                        serie_input.press_sequentially(serie, delay=50)
                        serie_input.press("Tab")
                        page.wait_for_timeout(500)

                    numero_input = iframe.locator("input#criterio\\.numero").first
                    if numero_input.count() > 0:
                        numero_input.click()
                        numero_input.fill("")
                        numero_input.press_sequentially(str(int(numero)), delay=50)
                        numero_input.press("Tab")
                        page.wait_for_timeout(500)

                    if fecha_emision_str:
                        fec_desde = iframe.locator("input#criterio\\.fecDesde").first
                        if fec_desde.count() > 0:
                            fec_desde.click()
                            fec_desde.fill("")
                            fec_desde.press_sequentially(fecha_emision_str, delay=50)
                            fec_desde.press("Tab")
                            page.wait_for_timeout(500)
                            
                        fec_hasta = iframe.locator("input#criterio\\.fecHasta").first
                        if fec_hasta.count() > 0:
                            fec_hasta.click()
                            fec_hasta.fill("")
                            fec_hasta.press_sequentially(fecha_emision_str, delay=50)
                            fec_hasta.press("Tab")
                            page.wait_for_timeout(500)
                    
                    btn_buscar = iframe.locator("#criterio\\.btnContinuar, #btnBuscar, button:has-text('Buscar'), input[value='Buscar']").first
                    btn_buscar.click(force=True)
                    
                    btn_visualizar = iframe.locator("a:has(img[src*='viewdoc.gif']), a[onclick*='consultaFactura.view'], a[title*='Visualizar'], button[title*='Visualizar'], img[title*='Visualizar'], img[alt*='Visualizar'], a:has(img[src*='impresora']), a:has(img[src*='pdf'])").first
                    
                    try:
                        btn_visualizar.wait_for(state="attached", timeout=10000)
                    except Exception:
                        pass
                    
                    if btn_visualizar.count() > 0:
                        log(f"Abriendo popup para {serie_num}")
                        with context.expect_page(timeout=15000) as popup_info:
                            btn_visualizar.click()
                        popup = popup_info.value
                        popup.wait_for_load_state("domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1000)

                        PALABRAS_EXCLUIR = {
                            "cant.(a)", "u.m.", "código", "descripción", "valor unit.(b)",
                            "precio unit.", "valor v.(a)*(b)", "icbper",
                            "descuento", "total", "sumatoria", "importe",
                            "tipo de comprobante", "número", "fecha de emisión", "moneda",
                            "ruc", "razón social", "domicilio", "tipo de documento",
                            "numero de documento",
                        }
                        detalles = []
                        filas = popup.locator("table tr:has(td)")
                        count_filas = filas.count()
                        for i in range(count_filas):
                            celdas = filas.nth(i).locator("td").all_text_contents()
                            celdas = [c.strip() for c in celdas]
                            if len(celdas) >= 6:
                                primera = celdas[0].strip()
                                try:
                                    float(primera.replace(",", "").replace(" ", ""))
                                    desc = celdas[3] if len(celdas) > 3 else ""
                                    if any(p in desc.lower() for p in PALABRAS_EXCLUIR):
                                        continue
                                    detalles.append({
                                        "cantidad": primera,
                                        "unidad_medida": celdas[1] if len(celdas) > 1 else "",
                                        "codigo": celdas[2] if len(celdas) > 2 else "",
                                        "descripcion": desc,
                                        "valor_unitario": celdas[4] if len(celdas) > 4 else "",
                                        "precio_unitario": celdas[5] if len(celdas) > 5 else "",
                                        "valor_venta": celdas[6] if len(celdas) > 6 else "",
                                        "icbper": celdas[7] if len(celdas) > 7 else "",
                                    })
                                except ValueError:
                                    pass

                        resultados[serie_num] = detalles
                        popup.close()
                        log(f"{serie_num}: {len(detalles)} items extraidos")
                            
                    else:
                        log(f"No se encontro boton visualizar para {serie_num}")
                        page.screenshot(path=_ruta_log(f"no_visualizar_{serie_num.replace('-', '_')}.png"))
                        try:
                            html = iframe.locator("body").inner_html()
                            with open(_ruta_log(f"no_visualizar_{serie_num.replace('-', '_')}.html"), "w", encoding="utf-8") as f:
                                f.write(html)
                        except Exception:
                            pass
                        
                except Exception as e:
                    log(f"Error procesando {serie_num}: {str(e)}")
                    page.screenshot(path=_ruta_log(f"error_{serie_num.replace('-', '_')}.png"))

            return resultados

        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f"Fallo general: {str(e)}")
            return resultados
        finally:
            if browser:
                browser.close()


async def obtener_detalles(
    empresa: dict,
    comprobantes: list[dict],
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
    progreso: Callable[[int, str], None] | None = None,
) -> dict:
    password_cifrada = empresa.get("password")
    if not password_cifrada:
        raise ValueError("No hay contraseña SOL guardada para ejecutar el scraping")

    # `progreso` se invoca desde el hilo de Playwright: quien lo pase es
    # responsable de devolver el aviso a su propio loop.
    return await asyncio.to_thread(
        _scrape_detalles,
        empresa["ruc"],
        empresa["usuario"],
        decrypt_password(password_cifrada),
        comprobantes,
        debug,
        headed,
        slow_mo_ms,
        progreso,
    )

