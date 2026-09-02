# Flujo — Extracción de detalle (scraping)

La API SIRE no expone el detalle línea por línea de cada comprobante (productos, cantidades, valores unitarios) — solo totales. Ese detalle se extrae haciendo scraping del portal SOL, opcionalmente, después de sincronizar la propuesta.

## Por qué es un job asíncrono

Cada comprobante pendiente requiere navegar un formulario del portal SOL con Playwright, lo cual toma un par de segundos por comprobante. [POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/detalle](../endpoints/detalle.md) no espera a que termine: crea un [Job](../../app/domain/jobs.py) en estado `pendiente`, lo encola con `BackgroundTasks` y responde `202` de inmediato con el `job_id`. El cliente consulta el avance con [GET /api/v1/jobs/{job_id}](../endpoints/jobs.md).

## Pasos

1. [detalle_service.extraer](../../app/services/detalle_service.py:16) busca los comprobantes **de ese libro** en el periodo que todavía no tienen `detalle_sunat` guardado (`listar_sin_detalle`). Si no hay ninguno, el job se completa de inmediato con `procesados: 0`.

   El libro no es opcional en esa consulta: `serie_numero` no es único dentro de un periodo —el mismo `F001-1` puede existir como venta propia y como compra a un tercero—, así que sin él una extracción de ventas recogería comprobantes de compras y el detalle acabaría escrito en el documento equivocado.

2. [scraping_sunat.obtener_detalles](../../app/services/scraping_sunat.py) descifra la contraseña SOL de la empresa y lanza un navegador Chromium headless con Playwright.

3. [_hacer_login](../../app/services/scraping_sunat.py) navega el menú de SUNAT (`e-menu.sunat.gob.pe`), localiza el formulario de login SOL (que a veces vive en un iframe, a veces en la página principal), completa RUC/usuario/contraseña y detecta errores de credenciales inspeccionando tanto selectores de error conocidos como el texto plano de la página. Al final llama a `_verificar_sesion`, que confirma que el menú quedó abierto: SUNAT rechaza credenciales devolviendo el formulario en lugar de un mensaje, así que sin esa comprobación el scraping seguía contra una página anónima y el job terminaba en `completado` con cero detalles tras agotar el timeout de cada comprobante. Si la sesión no se abrió, lanza `SesionSolError` y el job muere ahí.

4. Por cada comprobante pendiente, [_scrape_detalles](../../app/services/scraping_sunat.py) navega a la consulta de "Factura, Boletas y Notas", completa el formulario de búsqueda (tipo de consulta, RUC de la contraparte, serie, número y fecha de emisión en formato `dd/mm/aaaa`) y abre el popup de detalle del comprobante encontrado, del que extrae la tabla de ítems.

   El combo «Tipo de consulta» decide en qué bandeja busca el portal, y el portal separa **una bandeja por tipo de documento**, no una por libro. Estas son sus opciones reales:

   ```
   FE Emitidas · FE Recibidas · NC Emitidas · NC Recibidas · ND Emitidas
   ND Recibidas · BVE Emitidas - OSE · NC-BVE Emitidas - OSE · ND-BVE Emitidas - OSE
   ```

   Por eso la bandeja se elige con `bandeja(comprobante, libro)`, a partir del `tipo_cp`:

   | `tipo_cp` | Compras | Ventas |
   |---|---|---|
   | `01` factura | FE Recibidas | FE Emitidas |
   | `03` boleta | — | BVE Emitidas - OSE |
   | `07` nota de crédito | NC Recibidas | NC Emitidas |
   | `08` nota de débito | ND Recibidas | ND Emitidas |

   Una nota que corrige una **boleta** va a `NC-BVE`/`ND-BVE`. Eso no se deduce de su `tipo_cp` —es 07 u 08 como cualquier otra—, sino del tipo del documento que modifica, que el RVIE manda en `documentoMod` y el mapeo guarda en `extra.documentos_modificados`.

   El rótulo se compara **entero**: `BVE Emitidas - OSE` es subcadena de `NC-BVE Emitidas - OSE`, así que un `has-text` acabaría eligiendo la bandeja de las notas.

   El criterio de RUC necesita un matiz aparte: en compras es el emisor y siempre es un RUC, pero en ventas es el receptor, que en boletas suele ser un DNI o no venir. En ventas sólo se rellena si tiene once dígitos; sin él, serie + número + fecha identifican el comprobante (`_criterio_ruc`). Un criterio vacío **no se escribe**: `fill` espera a que el campo sea editable, y en las bandejas de emitidas algunos llegan deshabilitados, de modo que esa espera se tragaba el timeout completo del paso en cada comprobante.

5. Si un comprobante falla, se reintenta una vez. Cuando el fallo es que la sesión SOL expiró (`_es_sesion_expirada`, que sólo da positivo si SUNAT devolvió el formulario de login), se vuelve a entrar antes del reintento; si ni así se recupera, se corta la vuelta y se devuelve lo ya extraído en lugar de perderlo.

   Una búsqueda sin resultados (`ComprobanteNoEncontrado`) **no** se reintenta: SUNAT devolvería lo mismo y cada ronda cuesta un timeout completo. Es un caso normal —hay comprobantes que el portal no lista en la bandeja consultada—, no un error.

6. Cada comprobante con detalle encontrado se guarda vía `guardar_detalle_sunat`, que solo agrega el campo `detalle_sunat` sin tocar el resto del documento. El filtro incluye el libro, por lo mismo del paso 1.

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

El scraping abre un Chromium por trabajo y la API corre con un solo worker, así que dos extracciones simultáneas se pelean por la RAM y por la sesión SOL, que es única por usuario. Pero eso no tiene por qué costarle al usuario un rechazo: los trabajos de una misma empresa **se encolan**.

- **Mismo periodo y mismo libro ya en marcha** → `409`. Es un duplicado: dos trabajos raspando exactamente lo mismo.
- **Otro libro u otro periodo** → `202` con su `job_id`. El trabajo queda en `pendiente`, con el mensaje «En cola: hay otra extracción en curso», y arranca solo cuando el anterior termina.

Así se puede lanzar compras y ventas seguidas sin estar pendiente de cuándo acaba la primera. La cola es un `asyncio.Lock` por RUC en `jobs_service`: vive en el proceso, lo que basta porque la API corre con un único worker. Con varias réplicas haría falta un candado en Mongo.

Un fallo libera la cola (`async with`), así que un job que revienta no deja a la empresa sin poder extraer. Lo que sí se pierde son los `pendiente` si el proceso se reinicia: es la misma limitación que ya tenía `BackgroundTasks`.

En el frontend, la barra de progreso sigue **al libro seleccionado**. Sin ese filtro, una extracción de compras pintaba su avance bajo la vista de ventas —«Extrayendo E001-789 (6 de 87)» en un libro que sólo tiene 4 comprobantes—; el job de otro libro se anuncia aparte, en una línea de texto.

## Estado por libro

**Compras está verificado** de punta a punta contra el portal: una factura real devuelve sus ítems.

**Ventas no lo está.** La selección de bandeja por tipo de comprobante y el arreglo del criterio vacío son correctos —la búsqueda ya termina en vez de agotar el timeout—, pero una boleta real no aparece en `BVE Emitidas - OSE`. Quedan dos hipótesis sin descartar:

1. **La lista del combo está paginada.** «Opciones anteriores» y «Más opciones» son los controles de paginación de Dojo, así que puede haber bandejas que no se han visto todavía; `BVE … OSE` es específicamente para boletas emitidas a través de un OSE, y una empresa que no use OSE tendría la suya en otra.
2. **Falta un criterio.** El formulario tiene `criterio.numDocideRecep`, que no se rellena nunca. Para una boleta el receptor se identifica por DNI, y ese campo es el sitio natural para él.

Confirmarlo exige volver al portal. Conviene espaciar los intentos: SUNAT empieza a rechazar el login tras varias entradas seguidas.
