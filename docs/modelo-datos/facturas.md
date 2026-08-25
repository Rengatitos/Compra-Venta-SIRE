# Modelo de datos — facturas

Un comprobante de compra (factura o recibo por honorarios) sincronizado desde SIRE. Poblada inicialmente por [procesar_y_guardar_comprobantes](../../app/services/sire_service.py:46) mediante upsert, y enriquecida después por el scraping de detalle y por el análisis con IA.

| Campo | Origen | Descripción |
|---|---|---|
| usuario, periodo, número de serie | Sincronización SIRE | Clave lógica del documento, respaldada por el índice único parcial (ver [índices](indices.md)). El número de serie tiene el formato serie-número, por ejemplo F001-123. |
| estado de procesamiento | SIRE, luego IA | Pasa de recibida de SIRE (recién sincronizada) a analizada, a error de análisis, o a sin datos, tras el análisis con IA. Ver [flujo de análisis con IA](../flujo/05-analisis-ia.md). |
| RUC del emisor, nombre del proveedor | Sincronización SIRE, se refresca en cada sincronización | Ver las reglas de resolución de estos campos en [flujo de sincronización SIRE](../flujo/03-sincronizacion-sire.md). |
| fecha de emisión, fecha anterior | Sincronización SIRE | Formato día/mes/año. La fecha anterior es la fecha de emisión menos un día; su uso no está documentado explícitamente en ningún consumidor visible del código, probablemente pensado para filtros de rango en integraciones externas. |
| total, IGV | Sincronización SIRE | Montos numéricos. |
| tipo de operación | Sincronización SIRE | Siempre compras en el código actual. Existe soporte de filtrado por tipo de operación en analytics pensado para una futura extensión a ventas, pero la sincronización actual solo escribe compras. |
| datos crudos de SUNAT | Sincronización SIRE | El JSON completo del comprobante tal como lo devuelve la API SIRE, serializado como texto. Es el insumo principal para el análisis con IA. |
| detalle de compras de SUNAT | Scraping opcional | Lista de ítems (cantidad, unidad de medida, código, descripción, valor unitario, precio unitario, valor de venta, ICBPER) extraída del portal de SUNAT. Ausente si nunca se corrió el scraping para esa factura. Ver [flujo de scraping de detalle](../flujo/04-scraping-detalle.md). |
| metadata procesada | IA | Resultado de [extraer_datos_factura](../../app/services/analisis_ia.py:170): detalle (líneas contables), cuenta contable, centro de costos, condición de IGV, resultado de la clasificación, nivel de confianza de la IA, estado de la IA, documentos, descripción, observaciones, más el identificador de referencia (igual al número de serie, agregado por [procesar_lote_extracciones](../../app/services/analisis_ia.py:246)). Puede estar guardado como objeto o como cadena JSON, dependiendo de qué ruta lo haya escrito por última vez — el endpoint de análisis guarda un objeto, mientras que la actualización de factura preserva el tipo original al editar la descripción. Por eso [parse_metadata](../../app/services/invoice_service.py:19) soporta ambas representaciones. |

Índices: compuesto por usuario y periodo; suelto sobre el número de serie; único parcial por usuario, periodo y número de serie, cuya condición parcial excluye documentos con número de serie vacío o ausente, para no romper el índice único con datos legados que no lo tuvieran. Ver [índices](indices.md) para el resumen completo y [ciclo de vida](../arquitectura/ciclo-de-vida.md) para el manejo de errores al crear este índice.
