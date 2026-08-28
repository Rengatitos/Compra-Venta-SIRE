# Flujo — Extracción de detalle (scraping)

La API SIRE no expone el detalle línea por línea de cada comprobante (productos, cantidades, valores unitarios) — solo totales. Ese detalle se extrae haciendo scraping del portal SOL, opcionalmente, después de sincronizar la propuesta.

## Por qué es un job asíncrono

Cada comprobante pendiente requiere navegar un formulario del portal SOL con Playwright, lo cual toma varios segundos por comprobante. [POST /api/v1/empresas/{ruc}/periodos/{periodo}/detalle](../endpoints/detalle.md) no espera a que termine: crea un [Job](../../app/domain/jobs.py) en estado `pendiente`, lo encola con `BackgroundTasks` y responde `202` de inmediato con el `job_id`. El cliente consulta el avance con [GET /api/v1/jobs/{job_id}](../endpoints/jobs.md).

## Pasos

1. [detalle_service.extraer](../../app/services/detalle_service.py:15) busca los comprobantes del periodo que todavía no tienen `detalle_sunat` guardado ([listar_sin_detalle](../../app/repositories/comprobantes.py:168)). Si no hay ninguno, el job se completa de inmediato con `procesados: 0`.

2. [scraping_sunat.obtener_detalles](../../app/services/scraping_sunat.py) descifra la contraseña SOL de la empresa y lanza un navegador Chromium headless con Playwright.

3. [_hacer_login](../../app/services/scraping_sunat.py:22) navega el menú de SUNAT (`e-menu.sunat.gob.pe`), localiza el formulario de login SOL (que a veces vive en un iframe, a veces en la página principal), completa RUC/usuario/contraseña y detecta errores de credenciales inspeccionando tanto selectores de error conocidos como el texto plano de la página.

4. Por cada comprobante pendiente, [_scrape_detalles](../../app/services/scraping_sunat.py) navega a la consulta de "Factura, Boletas y Notas", completa el formulario de búsqueda (tipo de consulta "FE Recibidas", RUC del emisor, serie, fecha de emisión en formato `dd/mm/aaaa`) y abre el popup de detalle del comprobante encontrado, del que extrae la tabla de ítems.

5. Cada comprobante con detalle encontrado se guarda vía [guardar_detalle_sunat](../../app/repositories/comprobantes.py:207), que solo agrega el campo `detalle_sunat` sin tocar el resto del documento.

6. El progreso se reporta a través del callback `reportar` que [jobs_service.ejecutar](../../app/services/jobs_service.py:34) inyecta, actualizando `progreso.actual`/`progreso.total` en la colección `jobs` conforme avanza. Al terminar, el job pasa a `completado` con el resultado `{"procesados": N, "con_detalle": M}`, o a `fallido` con el mensaje de la excepción si algo se rompe.

Este detalle, cuando existe, se incorpora al texto que recibe la IA en el [flujo de análisis](05-analisis-ia.md).
