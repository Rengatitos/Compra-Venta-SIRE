import asyncio
from datetime import datetime

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.core.encryption import decrypt_password

load_dotenv()

URL_MENU = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm"


def _hacer_login(page, ruc: str, usuario: str, password: str) -> None:
    """Login SOL compartido (maneja iframes y detección de errores).

    Usado por _scrape_credenciales y _scrape_detalles — antes cada uno tenía
    su propia copia, y la de _scrape_detalles no manejaba iframes ni errores.
    """
    page.goto(URL_MENU, wait_until="domcontentloaded", timeout=60000)

    # Detectar si el formulario está en un iframe
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

    # Hacer clic en opción "Por RUC" si existe
    if login_frame.locator("#btnPorRuc").count() > 0:
        login_frame.click("#btnPorRuc")

    # Rellenar campos de login
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

    # Verificar si hay mensajes de error que indiquen credenciales incorrectas
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

    # Check textual en el body por si fallan los selectores
    body_text = page.locator("body").text_content() or ""
    if "Usuario o Clave Incorrectos" in body_text or "el RUC es incorrecto" in body_text.lower():
        raise ValueError("Credenciales SOL incorrectas (detectado por texto en página)")

    # Si quedó en api-seguridad, regresar a menu para estabilizar sesión
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


def _leer_credenciales_visibles(page) -> tuple[str, str]:
    def get_value_robust(selector: str) -> str:
        try:
            # Intentar vía JS para saltar restricciones de visibilidad/estado
            return page.evaluate(f"document.querySelector('{selector}').value") or ""
        except Exception:
            return ""

    client_id = get_value_robust("#id-api").strip()
    client_secret = get_value_robust("#clave").strip()
    
    return client_id, client_secret


def _set_input_value(page, selector: str, value: str):
    field = page.locator(selector).first
    field.wait_for(state="visible", timeout=10000)
    
    # Verificar si está deshabilitado antes de interactuar
    is_disabled = field.evaluate("el => el.disabled")
    if is_disabled:
        return

    field.click()

def _esta_en_formulario_registro(page) -> bool:
    return (
        page.locator("#txt-name-api").count() > 0
        and page.locator("#txt-name-url").count() > 0
        and page.locator("button:has-text('Guardar')").count() > 0
    )


def _resolver_estado_credenciales(page, wait_ms: int = 3000) -> str:
    # Esperar un momento a que los inputs carguen sus valores
    page.wait_for_timeout(1000)
    
    c_id, c_secret = _leer_credenciales_visibles(page)
    
    if c_id and c_secret:
        return "existing_credentials"
    
    if _esta_en_formulario_registro(page):
        return "registration_form"
        
    return "registration_form"


def _scrape_credenciales(
    ruc: str,
    usuario: str,
    password: str,
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
) -> tuple:
    URL_CREDENCIALES = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm?action=execute&code=80.1.1.1.1&s=ww1"
    debug_logs = []

    def log(msg: str):
        line = f"{datetime.now().isoformat(timespec='seconds')} | {msg}"
        debug_logs.append(line)
        print(line)

    def hacer_login(page):
        _hacer_login(page, ruc, usuario, password)

    def abrir_pagina_credenciales(page) -> bool:
        page.goto(URL_CREDENCIALES, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(800)

        if _es_sesion_expirada(page):
            return False

        if page.locator("#id-api").count() > 0:
            return True

        if page.locator("#txt-name-api").count() > 0 and page.locator("button:has-text('Guardar')").count() > 0:
            return True

        try:
            page.wait_for_selector("#id-api, #txt-name-api", timeout=12000)
        except Exception:
            return False

    browser = None
    with sync_playwright() as p:
        try:
            log(f"Iniciando navegador. headed={headed}, slow_mo_ms={slow_mo_ms}, debug={debug}")
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

            acceso_ok = False
            for intento in range(1, 4):
                hacer_login(page)
                if abrir_pagina_credenciales(page):
                    acceso_ok = True
                    break

            if not acceso_ok:
                raise Exception("No se pudo abrir la pagina de credenciales.")

            estado_credenciales = _resolver_estado_credenciales(page)

            if estado_credenciales == "existing_credentials":
                existing_client_id, existing_client_secret = _leer_credenciales_visibles(page)
                return existing_client_id, existing_client_secret, {
                    "debug_logs": debug_logs,
                    "credentials_source": "existing_form",
                }

            # Si no existen credenciales, pasar de inmediato al formulario de registro.
            log("No se encontraron credenciales existentes.")

            _set_input_value(page, "#txt-name-api", "API_TEST_SIRE")

            _set_input_value(page, "#txt-name-url", "https://api-test.example.com")

            # Seleccionar Todos
            select_all_btn = page.locator("button.btn.btn-outline-secondary.btn-sm.mr-2:has-text('Seleccionar Todos')").first
            select_all_btn.wait_for(state="visible", timeout=10000)
            select_all_btn.click()

            # Alcance: Desktop
            desktop_radio = page.locator("input#Desktop").first
            desktop_radio.wait_for(state="visible", timeout=10000)
            desktop_radio.check(force=True)
            page.evaluate(
                """
                () => {
                    const element = document.querySelector('#Desktop');
                    if (!element) {
                        return false;
                    }
                    element.checked = true;
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                """
            )

            # Auth Contabilidad (checkbox)
            auth_contab = page.locator("input[type='checkbox'][id*='contabilidad'], input[type='checkbox'] + label:has-text('contabilidad')").first
            if auth_contab.count() > 0:
                try:
                    auth_contab.check(force=True)
                except Exception:
                    auth_contab.click(force=True)

            # Guardar
            save_btn = page.locator("form button.btn.btn-primary.mr-2[type='submit']:has-text('Guardar')").first
            save_btn.wait_for(state="visible", timeout=10000)
            save_btn.click()

            # Esperar a que se generen y aparezcan los valores
            page.wait_for_timeout(2000)
            
            # Esperar confirmación o modal si aparece
            try:
                confirm_btn = page.locator("button:has-text('Aceptar')").first
                if confirm_btn.count() > 0:
                    confirm_btn.click()
                    page.wait_for_timeout(1500)
            except Exception:
                pass
            
            # Esperar a que aparezcan las credenciales generadas
            page.wait_for_function(
                "() => document.querySelector('#id-api') && document.querySelector('#id-api').value.length > 5",
                timeout=30000,
            )

            client_id = page.locator("#id-api").input_value().strip()
            client_secret = page.locator("#clave").input_value().strip()

            if not client_id or not client_secret:
                raise Exception("No se extrajeron las credenciales desde el formulario SUNAT")

            return client_id, client_secret, {
                "debug_logs": debug_logs,
                "credentials_source": "generated",
            }
        except Exception as e:
            import traceback
            print(f"Error en al scrapear credenciales: {str(e)}")
            traceback.print_exc()
            current_url = "desconocida"
            try:
                current_url = page.url
            except Exception:
                pass

            raise Exception(
                f"Fallo scraping SUNAT: {e}."
            )
        finally:
            if browser:
                browser.close()


async def login_y_consultar(
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    periodo: str,
    db,
    user_db,
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
):
    users_col = user_db["sol_users"]
    empresa = await users_col.find_one({
        "tenant_id": tenant_id,
        "cliente_id": cliente_id,
        "cuenta_id": cuenta_id
    })
    if not empresa:
        raise Exception("Usuario no encontrado en la BD")

    existing_client_id = (empresa.get("sunat_client_id") or "").strip()
    existing_client_secret = (empresa.get("sunat_client_secret") or "").strip()

    if existing_client_id and existing_client_secret:
        return {
            "client_id": existing_client_id,
            "sunat_client_id": existing_client_id,
            "client_secret_preview": existing_client_secret[:6] + "...",
            "mensaje": "Credenciales SUNAT ya existentes.",
            "scraping_ejecutado": False,
        }

    sunat_password = empresa.get("password")
    if not sunat_password:
        raise Exception("No hay contraseña SOL guardada para ejecutar el scraping.")
    sunat_password = decrypt_password(sunat_password)

    # El periodo se mantiene solo por compatibilidad de ruta.
    _ = periodo

    client_id, client_secret, debug_info = await asyncio.to_thread(
        _scrape_credenciales,
        empresa["ruc"],
        empresa["usuario"],
        sunat_password,
        debug,
        headed,
        slow_mo_ms,
    )

    # Guardar credenciales en BD
    await users_col.update_one(
        {"_id": empresa["_id"]},
        {"$set": {"sunat_client_id": client_id, "sunat_client_secret": client_secret}}
    )

    result = {
        "client_id": client_id,
        "sunat_client_id": client_id,
        "client_secret_preview": client_secret[:6] + "...",
        "mensaje": "Credenciales SUNAT guardadas correctamente",
        "scraping_ejecutado": True,
        "credentials_source": debug_info.get("credentials_source", "generated"),
    }

    if debug:
        result["debug_logs"] = debug_info.get("debug_logs", [])[-30:]

    return result


def _scrape_detalles(
    ruc: str,
    usuario: str,
    password: str,
    facturas_a_buscar: list[dict],
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
) -> dict:
    """
    Scrapea el detalle de los ítems para una lista de facturas.
    """
    URL_MENU = "https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm"
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

            # --- LOGIN (helper compartido con _scrape_credenciales) ---
            _hacer_login(page, ruc, usuario, password)
            page.wait_for_timeout(3000)

            # --- NAVEGAR AL MENÚ DE CONSULTA DE FACTURAS ---
            try:
                # Empresas
                tab_empresas = page.locator("#btnEmpresas, a:has-text('Empresas')").first
                if tab_empresas.count() > 0:
                    tab_empresas.click()
                    page.wait_for_timeout(2000)
                    
            except Exception as e:
                log(f"Error navegando menú principal: {e}")

            page.wait_for_timeout(3000)
            
            iframe = page.frame_locator("#iframeApplication")
            
            for fac in facturas_a_buscar:
                # RECARGAMOS el menu para cada factura para evitar que se quede en la tabla de resultados
                try:
                    page.evaluate("if(typeof ejecuta === 'function'){ ejecuta('MenuInternet.htm?action=iconExecute&code=11.9.5.1.1',false,'Consultar Factura, Boletas y Notas','#nivel1_11','11.9.5.1.1'); }")
                    # Esperar a que el campo tipoConsulta sea visible: señal de que el form Dojo inicializó
                    iframe.locator("input#criterio\\.tipoConsulta").wait_for(state="visible", timeout=15000)
                    page.wait_for_timeout(500)
                except Exception as e:
                    log(f"Error cargando iframe: {e}")
                    page.screenshot(path="/app/logs/error_iframe_timeout.png")
                    continue
                
                serie_num = fac.get("serie_numero", "")
                ruc_emisor = fac.get("ruc_emisor", "")
                fecha_emision = fac.get("fecha_emision", "")
                
                if not serie_num or "-" not in serie_num:
                    continue
                    
                serie, numero = serie_num.split("-", 1)
                log(f"Buscando factura: {serie_num}")

                try:
                    # Parsear la fecha de emision a dd/mm/yyyy
                    fecha_emision_str = ""
                    if fecha_emision:
                        if "T" in fecha_emision:
                            # 2026-02-15T...
                            ymd = fecha_emision.split("T")[0].split("-")
                            if len(ymd) == 3:
                                fecha_emision_str = f"{ymd[2]}/{ymd[1]}/{ymd[0]}"
                        elif "-" in fecha_emision:
                            ymd = fecha_emision.split(" ")[0].split("-")
                            if len(ymd) == 3:
                                fecha_emision_str = f"{ymd[2]}/{ymd[1]}/{ymd[0]}"
                        elif "/" in fecha_emision:
                            fecha_emision_str = fecha_emision.split(" ")[0]
                    
                    if not fecha_emision_str:
                        # Fallback a un rango amplio o el mes actual si no hay fecha?
                        pass

                    # 1. Tipo de Consulta
                    combo = iframe.locator("input#criterio\\.tipoConsulta").first
                    if combo.count() > 0:
                        combo.click()
                        combo.fill("")
                        page.wait_for_timeout(500)
                        combo.press_sequentially("FE Recibidas", delay=100)
                        page.wait_for_timeout(1500) # Esperar a que Dojo abra el popup
                        
                        opcion_popup = iframe.locator("li.dijitMenuItem:has-text('FE Recibidas'), li.dijitMenuItem:has-text('Recibidas')").first
                        if opcion_popup.count() > 0:
                            opcion_popup.click()
                        else:
                            combo.press("ArrowDown")
                            page.wait_for_timeout(300)
                            combo.press("Enter")
                        page.wait_for_timeout(1000)

                    # 2. RUC Emisor
                    ruc_input = iframe.locator("input#criterio\\.ruc").first
                    if ruc_input.count() > 0:
                        ruc_input.click()
                        ruc_input.fill("")
                        ruc_input.press_sequentially(ruc_emisor, delay=50)
                        ruc_input.press("Tab")
                        page.wait_for_timeout(500)

                    # 3. Serie
                    serie_input = iframe.locator("input#criterio\\.serie").first
                    if serie_input.count() > 0:
                        serie_input.click()
                        serie_input.fill("")
                        serie_input.press_sequentially(serie, delay=50)
                        serie_input.press("Tab")
                        page.wait_for_timeout(500)

                    # 4. Número
                    numero_input = iframe.locator("input#criterio\\.numero").first
                    if numero_input.count() > 0:
                        numero_input.click()
                        numero_input.fill("")
                        numero_input.press_sequentially(str(int(numero)), delay=50)
                        numero_input.press("Tab")
                        page.wait_for_timeout(500)

                    # 5. Fechas (Desde y Hasta)
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
                    
                    # Click buscar
                    btn_buscar = iframe.locator("#criterio\\.btnContinuar, #btnBuscar, button:has-text('Buscar'), input[value='Buscar']").first
                    btn_buscar.click(force=True)
                    
                    # Esperar tabla de resultados o el botón visualizar (puede tardar un poco en cargar por red)
                    btn_visualizar = iframe.locator("a:has(img[src*='viewdoc.gif']), a[onclick*='consultaFactura.view'], a[title*='Visualizar'], button[title*='Visualizar'], img[title*='Visualizar'], img[alt*='Visualizar'], a:has(img[src*='impresora']), a:has(img[src*='pdf'])").first
                    
                    try:
                        btn_visualizar.wait_for(state="attached", timeout=10000)
                    except Exception:
                        pass
                    
                    if btn_visualizar.count() > 0:
                        # Visualizar abre un popup en ww1.sunat.gob.pe (dominio diferente)
                        log(f"Abriendo popup para {serie_num}")
                        with context.expect_page(timeout=15000) as popup_info:
                            btn_visualizar.click()
                        popup = popup_info.value
                        popup.wait_for_load_state("domcontentloaded", timeout=15000)
                        page.wait_for_timeout(1000)

                        # Extraer ítems: solo filas donde cantidad es numérico
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
                        page.screenshot(path=f"/app/logs/no_visualizar_{serie_num.replace('-', '_')}.png")
                        try:
                            html = iframe.locator("body").inner_html()
                            with open(f"/app/logs/no_visualizar_{serie_num.replace('-', '_')}.html", "w", encoding="utf-8") as f:
                                f.write(html)
                        except:
                            pass
                        
                except Exception as e:
                    log(f"Error procesando {serie_num}: {str(e)}")
                    page.screenshot(path=f"/app/logs/error_{serie_num.replace('-', '_')}.png")

            return resultados

        except Exception as e:
            import traceback
            traceback.print_exc()
            log(f"Fallo general: {str(e)}")
            return resultados
        finally:
            if browser:
                browser.close()


async def obtener_detalles_facturas_recibidas(
    tenant_id: str,
    cliente_id: str,
    cuenta_id: str,
    facturas_a_buscar: list[dict],
    user_db,
    debug: bool = False,
    headed: bool = False,
    slow_mo_ms: int = 0,
):
    users_col = user_db["sol_users"]
    empresa = await users_col.find_one({
        "tenant_id": tenant_id,
        "cliente_id": cliente_id,
        "cuenta_id": cuenta_id
    })
    if not empresa:
        raise Exception("Usuario no encontrado en la BD")

    sunat_password = empresa.get("password")
    if not sunat_password:
        raise Exception("No hay contraseña SOL guardada para ejecutar el scraping.")
    sunat_password = decrypt_password(sunat_password)

    resultados = await asyncio.to_thread(
        _scrape_detalles,
        empresa["ruc"],
        empresa["usuario"],
        sunat_password,
        facturas_a_buscar,
        debug,
        headed,
        slow_mo_ms,
    )
    
    return resultados

