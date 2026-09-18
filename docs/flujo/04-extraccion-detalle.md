# Flujo — Extracción de detalle (scraping)

La API SIRE no expone el detalle línea por línea de cada comprobante (productos, cantidades, valores unitarios) — solo totales. Ese detalle se extrae haciendo scraping del portal SOL, opcionalmente, después de sincronizar la propuesta.

## Por qué es un job asíncrono

Cada comprobante pendiente requiere navegar un formulario del portal SOL con Playwright, lo cual toma un par de segundos por comprobante. [POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/detalle](../endpoints/detalle.md) no espera a que termine: crea un [Job](../../app/domain/jobs.py) en estado `pendiente`, lo encola con `BackgroundTasks` y responde `202` de inmediato con el `job_id`. El cliente consulta el avance con [GET /api/v1/jobs/{job_id}](../endpoints/jobs.md).

## Pasos

1. `detalle_service.extraer` ([detalle_service.py](../../app/services/detalle_service.py)) busca los comprobantes **de ese libro** en el periodo a los que les falta el detalle o el PDF (`listar_pendientes_sunat`). Quedan fuera los tipos que SUNAT no publica y las boletas recibidas de serie B en compras (ver [glosa y estado](05-glosa-y-estado.md)): el job los cuenta en `omitidos_sin_detalle` y lo dice en su primer mensaje. Si no hay ninguno pendiente, el job se completa de inmediato con `procesados: 0`.

   El libro no es opcional en esa consulta: `serie_numero` no es único dentro de un periodo —el mismo `F001-1` puede existir como venta propia y como compra a un tercero—, así que sin él una extracción de ventas recogería comprobantes de compras y el detalle acabaría escrito en el documento equivocado.

2. [scraping_sunat.obtener_detalles](../../app/services/scraping_sunat.py) descifra la contraseña SOL de la empresa y lanza un navegador Chromium headless con Playwright.

3. [_hacer_login](../../app/services/scraping_sunat.py) navega el menú de SUNAT (`e-menu.sunat.gob.pe`), localiza el formulario de login SOL (que a veces vive en un iframe, a veces en la página principal), completa RUC/usuario/contraseña y detecta errores de credenciales inspeccionando tanto selectores de error conocidos como el texto plano de la página. Al final llama a `_verificar_sesion`, que confirma que el menú quedó abierto: SUNAT rechaza credenciales devolviendo el formulario en lugar de un mensaje, así que sin esa comprobación el scraping seguía contra una página anónima y el job terminaba en `completado` con cero detalles tras agotar el timeout de cada comprobante. Si la sesión no se abrió, lanza `SesionSolError` y el job muere ahí.

4. Por cada comprobante pendiente, [_scrape_detalles](../../app/services/scraping_sunat.py) navega a la consulta de "Factura, Boletas y Notas", completa el formulario de búsqueda (tipo de consulta, RUC de la contraparte, serie, número y fecha de emisión en formato `dd/mm/aaaa`) y abre el popup de detalle del comprobante encontrado, del que extrae la tabla de ítems.

   El combo «Tipo de consulta» decide en qué bandeja busca el portal, y el portal separa **una bandeja por tipo de documento**, no una por libro. Estas son sus opciones reales, y son **todas**: `scripts/listar_bandejas_sol.py` recorrió el combo completo el 18 de septiembre de 2026 y no hay más páginas ni una bandeja de boletas recibidas.

   ```
   FE Emitidas · FE Recibidas · NC Emitidas · NC Recibidas · ND Emitidas
   ND Recibidas · BVE Emitidas - OSE · NC-BVE Emitidas - OSE · ND-BVE Emitidas - OSE
   ```

   Por eso la bandeja se elige con `bandeja(comprobante, libro)`, a partir del `tipo_cp`:

   | `tipo_cp` | Compras | Ventas |
   |---|---|---|
   | `01` factura | FE Recibidas | FE Emitidas |
   | `03` boleta | — (sin bandeja: no se consulta; las EB01 van por SEE-SOL) | BVE Emitidas - OSE |
   | `07` nota de crédito | NC Recibidas | NC Emitidas |
   | `08` nota de débito | ND Recibidas | ND Emitidas |

   Un tipo sin bandeja cae en la de facturas, pero eso ya sólo puede pasar con los 14 tipos que esperan casos reales (13, 14, 18…), porque los que SUNAT no publica no entran al job.

   Una nota que corrige una **boleta** va a `NC-BVE`/`ND-BVE`. Eso no se deduce de su `tipo_cp` —es 07 u 08 como cualquier otra—, sino del tipo del documento que modifica, que el RVIE manda en `documentoMod` y el mapeo guarda en `extra.documentos_modificados`.

   El rótulo se compara **entero**: `BVE Emitidas - OSE` es subcadena de `NC-BVE Emitidas - OSE`, así que un `has-text` acabaría eligiendo la bandeja de las notas.

   El criterio de RUC necesita un matiz aparte: en compras es el emisor y siempre es un RUC, pero en ventas es el receptor, que en boletas suele ser un DNI o no venir. En ventas el RUC sólo se rellena si tiene once dígitos (`_criterio_ruc`); si el receptor es un DNI u otro documento, va en el criterio `numDocideRecep` del formulario (`_criterio_doc_receptor`), que compras no usa. Un criterio vacío **no se escribe**: `fill` espera a que el campo sea editable, y en las bandejas de emitidas algunos criterios llegan deshabilitados, de modo que esa espera se tragaba el timeout completo del paso en cada comprobante.

   **Series E (SEE-SOL).** Los comprobantes emitidos desde el portal de SUNAT (facturas `E001`, boletas `EB01`, notas `EC`/`ED`) no están en estas bandejas: `_es_serie_sol` los desvía a `_consultar_uno_see_sol`, que entra al módulo SEE-SOL correspondiente (facturas o boletas, códigos de menú `11.5.3.1.2` y `11.5.4.1.4`), pide por HTTP dentro de la sesión el listado del mes con el `tipoConsulta` que corresponde al libro y tipo (`_ruta_see_sol`), localiza la fila del comprobante por RUC emisor, tipo, serie y número, y abre su impresión (`verImprimirFactura`) en una pestaña aparte, de la que lee la tabla de ítems y captura el PDF. El índice de la fila sólo vale para la última consulta de la sesión, así que las dos peticiones van seguidas. Cuando el comprobante no está, el log dice cuántas filas listó el portal ese mes. Verificado el 18 de septiembre de 2026 con siete facturas E001 recibidas y cuatro boletas EB01 emitidas: todas con ítems y PDF.

5. Si un comprobante falla, se reintenta una vez. Cuando el fallo es que la sesión SOL expiró (`_es_sesion_expirada`, que sólo da positivo si SUNAT devolvió el formulario de login), se vuelve a entrar antes del reintento; si ni así se recupera, se corta la vuelta y se devuelve lo ya extraído en lugar de perderlo.

   Pulsar Buscar tiene **tres** desenlaces y `_esperar_resultado` los separa sondeando el iframe cada 250 ms:

   - aparece el enlace «Visualizar» y se sigue;
   - el portal avisa de que no hay resultados (uno de los textos de `SUNAT_TEXTOS_SIN_RESULTADOS`) → `ComprobanteNoEncontrado`, que **no** se reintenta: SUNAT devolvería lo mismo. Es un caso normal —hay comprobantes que el portal no lista en la bandeja consultada—, no un error;
   - se agota el plazo sin ninguna de las dos cosas → `BusquedaSinRespuesta`, que **sí** se reintenta.

   Confundir los dos últimos era un fallo real: BBVA y BCP tardan unos 9 s en responder, pasaban del techo de 8 s que había antes y se registraban como «SUNAT no lo tiene», quedándose sin detalle y sin PDF pese a estar en el portal.

6. Cada comprobante con detalle encontrado se guarda vía `guardar_detalle_sunat`, que solo agrega el campo `detalle_sunat` sin tocar el resto del documento. El filtro incluye el libro, por lo mismo del paso 1.

7. El progreso se reporta a través del callback `reportar` que `jobs_service.ejecutar` ([jobs_service.py](../../app/services/jobs_service.py)) inyecta, actualizando `progreso.actual`/`progreso.total` en la colección `jobs` conforme avanza. Al terminar, el job pasa a `completado` con el resultado `{"procesados", "con_detalle", "sin_detalle", "descargados_pdf", "sin_pdf", "pendientes", "omitidos_sin_detalle"}`, o a `fallido` con el mensaje de la excepción si algo se rompe. `pendientes` es lo que quedó fuera por el tope de `SUNAT_MAX_COMPROBANTES`; `omitidos_sin_detalle`, lo que no se consulta porque SUNAT no lo publica. Cada comprobante que el scraper buscó —encontrado o no— queda marcado con `glosa_consultada`, que es lo que separa «sin glosa» de «pendiente».


## Rendimiento

El recorrido costaba unos 15 s por comprobante, de los cuales ~10 s eran espera artificial: `wait_for_timeout` fijos y `press_sequentially` tecleando letra por letra. Hoy son ~2 s. Los cambios que lo consiguieron:

- Los campos de texto se rellenan con `fill()` + `Tab` (helper `_llenar`) en vez de teclear con 50 ms de retardo por carácter y medio segundo de cortesía detrás.
- Las esperas fijas se cambiaron por esperas por condición: la lista del combo Dojo, la tabla del popup y el fin de la navegación tras el login.
- La tabla de ítems se lee con una sola llamada al navegador (`_JS_LEER_TABLA`) en lugar de un round-trip por fila, y se parsea en Python con `_parsear_filas`.
- Las capturas de pantalla de diagnóstico solo se toman con `debug=True`; escribirlas en disco estaba en el camino caliente.

El coste dominante que queda es la recarga del iframe entre comprobantes (~0,9 s de los ~2 s). Los comprobantes que SUNAT no lista ya no cuestan un timeout completo cada uno: `_esperar_resultado` reconoce el aviso de "sin resultados" del portal y los descarta al instante. Eso es lo que permitió subir `SUNAT_TIMEOUT_BUSQUEDA_MS` a 25 s sin encarecer nada — ahora ese plazo sólo lo agotan los emisores que de verdad tardan.

El guardado ocurre **conforme llega cada comprobante** (`al_extraer`), no al final: antes un tropiezo a mitad de la lista tiraba todo lo ya recorrido.

## Ajustes

En [config.py](../../app/core/config.py):

| Ajuste | Por defecto | Para qué |
|---|---|---|
| `SUNAT_SCRAPER_HEADLESS` | `True` | Ponerlo en `False` abre el navegador visible, útil para diagnosticar cambios del portal. |
| `SUNAT_SCRAPER_TIMEOUT_MS` | `15000` | Techo de espera de cada paso de Playwright. |
| `SUNAT_TIMEOUT_BUSQUEDA_MS` | `25000` | Cuánto esperar una respuesta a la búsqueda. No es el plazo para darlo por inexistente: los ausentes salen al instante por el aviso del portal, así que este techo sólo lo agotan los emisores lentos (los bancos rondan los 9 s). |
| `SUNAT_TEXTOS_SIN_RESULTADOS` | ver `config.py` | Avisos con los que el portal dice que no hay resultados; se comparan como subcadena y sin distinguir mayúsculas. Conviene quedarse corto: uno que no casa sólo cuesta esperar el techo de arriba, mientras que uno demasiado amplio da por ausente un comprobante que sí está. No se documenta en `.env.example` porque, al ser un tipo compuesto, pydantic-settings lo lee como JSON. |
| `SUNAT_MAX_COMPROBANTES` | `100` | Cuántos se piden como máximo por extracción. Lo que sobra se reporta en `pendientes` y necesita otra vuelta. |

## Un job a la vez por empresa

El scraping abre un Chromium por trabajo y la API corre con un solo worker, así que dos extracciones simultáneas se pelean por la RAM y por la sesión SOL, que es única por usuario. Pero eso no tiene por qué costarle al usuario un rechazo: los trabajos de una misma empresa **se encolan**.

- **Mismo periodo y mismo libro ya en marcha** → `409`. Es un duplicado: dos trabajos raspando exactamente lo mismo.
- **Otro libro u otro periodo** → `202` con su `job_id`. El trabajo queda en `pendiente`, con el mensaje «En cola: hay otra extracción en curso», y arranca solo cuando el anterior termina.

Así se puede lanzar compras y ventas seguidas sin estar pendiente de cuándo acaba la primera. La cola es un `asyncio.Lock` por RUC en `jobs_service`: vive en el proceso, lo que basta porque la API corre con un único worker. Con varias réplicas haría falta un candado en Mongo.

Un fallo libera la cola (`async with`), así que un job que revienta no deja a la empresa sin poder extraer. Lo que sí se pierde son los `pendiente` si el proceso se reinicia: es la misma limitación que ya tenía `BackgroundTasks`.

En el frontend, la barra de progreso sigue **al libro seleccionado**. Sin ese filtro, una extracción de compras pintaba su avance bajo la vista de ventas —«Extrayendo E001-789 (6 de 87)» en un libro que sólo tiene 4 comprobantes—; el job de otro libro se anuncia aparte, en una línea de texto.

## Estado por libro

**Compras está verificado** de punta a punta contra el portal, tanto por bandeja (facturas `F…`) como por SEE-SOL (facturas `E001`): los comprobantes reales devuelven sus ítems y su PDF.

**Ventas está verificado para boletas SEE-SOL** (`EB01`, el caso real disponible: cuatro boletas con DNI del receptor, todas con ítems y PDF). Lo que queda sin caso real es una boleta `B…` emitida por OSE/PSE, que iría por la bandeja `BVE Emitidas - OSE` con el DNI en `numDocideRecep`; el criterio ya se rellena, falta un RUC que emita así para confirmarlo. La hipótesis de que el combo tuviera más bandejas quedó descartada al enumerarlo completo.

Conviene espaciar los intentos contra el portal: SUNAT empieza a rechazar el login tras varias entradas seguidas (el primer intento suele fallar y el segundo entra).
