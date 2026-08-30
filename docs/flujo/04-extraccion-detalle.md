# Flujo — Extracción de detalle (scraping)

La API SIRE no expone el detalle línea por línea de cada comprobante (productos, cantidades, valores unitarios) — solo totales. Ese detalle se extrae haciendo scraping del portal SOL, opcionalmente, después de sincronizar la propuesta.

## Por qué es un job asíncrono

Cada comprobante pendiente requiere navegar un formulario del portal SOL con Playwright, lo cual toma un par de segundos por comprobante. [POST /api/v1/empresas/{ruc}/periodos/{periodo}/detalle](../endpoints/detalle.md) no espera a que termine: crea un [Job](../../app/domain/jobs.py) en estado `pendiente`, lo encola con `BackgroundTasks` y responde `202` de inmediato con el `job_id`. El cliente consulta el avance con [GET /api/v1/jobs/{job_id}](../endpoints/jobs.md).

## Pasos

1. [detalle_service.extraer](../../app/services/detalle_service.py:15) busca los comprobantes del periodo que todavía no tienen `detalle_sunat` guardado ([listar_sin_detalle](../../app/repositories/comprobantes.py:168)). Si no hay ninguno, el job se completa de inmediato con `procesados: 0`.

2. [scraping_sunat.obtener_detalles](../../app/services/scraping_sunat.py) descifra la contraseña SOL de la empresa y lanza un navegador Chromium headless con Playwright.

3. [_hacer_login](../../app/services/scraping_sunat.py) navega el menú de SUNAT (`e-menu.sunat.gob.pe`), localiza el formulario de login SOL (que a veces vive en un iframe, a veces en la página principal), completa RUC/usuario/contraseña y detecta errores de credenciales inspeccionando tanto selectores de error conocidos como el texto plano de la página. Al final llama a `_verificar_sesion`, que confirma que el menú quedó abierto: SUNAT rechaza credenciales devolviendo el formulario en lugar de un mensaje, así que sin esa comprobación el scraping seguía contra una página anónima y el job terminaba en `completado` con cero detalles tras agotar el timeout de cada comprobante. Si la sesión no se abrió, lanza `SesionSolError` y el job muere ahí.

4. Por cada comprobante pendiente, [_scrape_detalles](../../app/services/scraping_sunat.py) navega a la consulta de "Factura, Boletas y Notas", completa el formulario de búsqueda (tipo de consulta "FE Recibidas", RUC del emisor, serie, fecha de emisión en formato `dd/mm/aaaa`) y abre el popup de detalle del comprobante encontrado, del que extrae la tabla de ítems.

5. Si un comprobante falla, se reintenta una vez. Cuando el fallo es que la sesión SOL expiró (`_es_sesion_expirada`, que sólo da positivo si SUNAT devolvió el formulario de login), se vuelve a entrar antes del reintento; si ni así se recupera, se corta la vuelta y se devuelve lo ya extraído en lugar de perderlo.

   Una búsqueda sin resultados (`ComprobanteNoEncontrado`) **no** se reintenta: SUNAT devolvería lo mismo y cada ronda cuesta un timeout completo. Es un caso normal —hay comprobantes que el portal no lista entre las FE recibidas—, no un error.

6. Cada comprobante con detalle encontrado se guarda vía [guardar_detalle_sunat](../../app/repositories/comprobantes.py:207), que solo agrega el campo `detalle_sunat` sin tocar el resto del documento.

7. El progreso se reporta a través del callback `reportar` que [jobs_service.ejecutar](../../app/services/jobs_service.py:34) inyecta, actualizando `progreso.actual`/`progreso.total` en la colección `jobs` conforme avanza. Al terminar, el job pasa a `completado` con el resultado `{"procesados": N, "con_detalle": M, "pendientes": P}`, o a `fallido` con el mensaje de la excepción si algo se rompe. `pendientes` es lo que quedó fuera por el tope de `SUNAT_MAX_COMPROBANTES`.

Este detalle, cuando existe, se incorpora al texto que recibe la IA en el [flujo de análisis](05-analisis-ia.md).

## Rendimiento

El recorrido costaba unos 15 s por comprobante, de los cuales ~10 s eran espera artificial: `wait_for_timeout` fijos y `press_sequentially` tecleando letra por letra. Hoy son ~2 s. Los cambios que lo consiguieron:

- Los campos de texto se rellenan con `fill()` + `Tab` (helper `_llenar`) en vez de teclear con 50 ms de retardo por carácter y medio segundo de cortesía detrás.
- Las esperas fijas se cambiaron por esperas por condición: la lista del combo Dojo, la tabla del popup y el fin de la navegación tras el login.
- La tabla de ítems se lee con una sola llamada al navegador (`_JS_LEER_TABLA`) en lugar de un round-trip por fila, y se parsea en Python con `_parsear_filas`.
- Las capturas de pantalla de diagnóstico solo se toman con `debug=True`; escribirlas en disco estaba en el camino caliente.

El coste dominante que queda es la recarga del iframe entre comprobantes (~0,9 s de los ~2 s) y, en periodos con comprobantes que SUNAT no lista, los `SUNAT_TIMEOUT_BUSQUEDA_MS` de cada uno. Detectar el marcador de "sin resultados" del portal permitiría descartarlos al instante, pero hace falta capturar ese HTML sin que SUNAT corte la conexión por exceso de accesos.

El guardado ocurre **conforme llega cada comprobante** (`al_extraer`), no al final: antes un tropiezo a mitad de la lista tiraba todo lo ya recorrido.

## Ajustes

En [config.py](../../app/core/config.py):

| Ajuste | Por defecto | Para qué |
|---|---|---|
| `SUNAT_SCRAPER_HEADLESS` | `True` | Ponerlo en `False` abre el navegador visible, útil para diagnosticar cambios del portal. |
| `SUNAT_SCRAPER_TIMEOUT_MS` | `15000` | Techo de espera de cada paso de Playwright. |
| `SUNAT_TIMEOUT_BUSQUEDA_MS` | `8000` | Cuánto esperar antes de dar un comprobante por inexistente. Cuando SUNAT sí lo tiene, el enlace aparece en menos de un segundo, así que este techo sólo lo pagan los que faltan. |
| `SUNAT_MAX_COMPROBANTES` | `100` | Cuántos se piden como máximo por extracción. Lo que sobra se reporta en `pendientes` y necesita otra vuelta. |

## Un job a la vez por empresa

El scraping abre un Chromium por trabajo y la API corre con un solo worker, así que dos extracciones simultáneas se pelean por la RAM y por la sesión SOL, que es única por usuario. La ruta responde `409` si ya hay un job de detalle vivo para ese RUC (`jobs_service.activo`); el límite de `slowapi` es por IP y no bastaba para impedirlo.
