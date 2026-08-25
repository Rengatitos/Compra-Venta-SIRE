# Flujo — Scraping opcional de detalle de ítems

El endpoint [post_scrape_detalles](../endpoints/sire.md) dispara [procesar_detalles_scraper](../../app/services/sire_service.py:235) en segundo plano, sin bloquear la respuesta HTTP, que se devuelve de inmediato indicando que el proceso fue iniciado.

## Por qué existe

La API oficial de SIRE solo entrega los totales del comprobante, no el detalle línea por línea de los productos o servicios comprados. Ese detalle solo está disponible visualizando el comprobante directamente en el portal web de SUNAT — de ahí la necesidad del scraping. Este scraping ya no incluye la obtención de credenciales (ver [flujo de registro y login](01-registro-login.md)); el único uso que queda de Playwright en el sistema es la extracción de este detalle de ítems, en [obtener_detalles_facturas_recibidas](../../app/services/scraping_sunat.py:353).

## Proceso

Primero se seleccionan las facturas del periodo que aún no tienen detalle de compras registrado (hasta 100 por corrida). Luego, [_scrape_detalles](../../app/services/scraping_sunat.py:122) —una función síncrona que corre en un hilo separado para no bloquear el bucle de eventos— usa Playwright con Chromium en modo headless:

1. [_hacer_login](../../app/services/scraping_sunat.py:14) navega al menú de SUNAT Operaciones en Línea, localiza el formulario de login (con reintentos durante 20 segundos para manejar el caso de que el formulario esté embebido en un iframe), completa RUC, usuario y contraseña, y detecta errores de credenciales inválidas buscando mensajes de error conocidos o el texto literal correspondiente en la página.

2. Para cada factura pendiente: recarga el menú de consulta de comprobantes recibidos (necesario para no quedar atrapado en la tabla de resultados de la búsqueda anterior), completa el formulario de búsqueda dentro de un iframe (tipo de consulta de comprobantes recibidos, RUC del emisor, serie, número, y un rango de fechas igual a la fecha de emisión del comprobante), ejecuta la búsqueda y, si aparece el botón para visualizar el comprobante, abre la ventana emergente correspondiente (en un dominio distinto del portal principal) y extrae las filas de la tabla de ítems que tengan una cantidad numérica en la primera celda, descartando encabezados y totales mediante una lista de palabras a excluir.

3. Cada factura resuelta actualiza el campo de detalle de compras de SUNAT con la lista de ítems extraídos: cantidad, unidad de medida, código, descripción, valor unitario, precio unitario, valor de venta e ICBPER. Ver [modelo de datos de facturas](../modelo-datos/facturas.md).

Este paso es completamente opcional: el análisis con IA (ver [flujo de análisis con IA](05-analisis-ia.md)) funciona sin él, solo que sin el detalle real de ítems la clasificación se basa únicamente en los totales de los datos crudos que entrega SUNAT.
