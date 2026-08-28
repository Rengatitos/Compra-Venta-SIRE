# Flujo — Análisis con IA

[POST /api/v1/empresas/{ruc}/periodos/{periodo}/analisis](../endpoints/analisis.md) llama a [procesar_lote](../../app/services/analisis_ia.py:246).

## RAG de dos niveles

1. **Base global (normativa contable, PCGE).** Cargada una sola vez en memoria al arrancar el servidor con [cargar_vector](../../app/services/analisis_ia.py:28), leyendo la colección `vector_global` durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación. Compartida entre todas las empresas.

2. **RAG de empresa**, resuelto en la propia ruta de análisis, no en el servicio, con este orden de prioridad: primero, los PDFs adjuntados en la misma petición (procesados en memoria, no persistidos); si no se adjuntan, los chunks ya indexados en `vector_usuarios` para esa empresa, subidos previamente vía [referencias](../endpoints/referencias.md).

## Detalles del proceso

El cliente de Gemini, en [_get_client](../../app/services/analisis_ia.py:18), se construye de forma perezosa en el primer uso, no al importar el módulo, y valida `GEMINI_API_KEY` en ese momento — si falta, falla con un `RuntimeError` explícito en la primera llamada, no en silencio ni al arrancar toda la aplicación.

[buscar_contexto](../../app/services/analisis_ia.py:111) genera el embedding del texto del comprobante y calcula similitud de coseno contra cada elemento de la base global y de la de la empresa, en memoria (no hay índice vectorial de base de datos), devolviendo los veinte resultados más relevantes de cada fuente como texto plano de contexto.

[extraer_datos_factura](../../app/services/analisis_ia.py:170) arma un prompt con reglas de negocio explícitas sobre la serie del comprobante (F = factura de bienes/servicios, E = recibo por honorarios), el contexto normativo recuperado, y le pide a `gemini-2.5-flash` — configurado para responder en JSON estricto — un resultado con: el detalle de líneas (producto, categoría contable, cantidad, importe, razón), la cuenta contable sugerida (código PCGE), el centro de costos, la condición de IGV, el resultado de la clasificación (`COSTO`/`GASTO`/`ACTIVO`/`NO DETERMINADO`), el nivel de confianza, el estado (`Analizado`/`Requiere revision humana`), una descripción y observaciones.

El texto que recibe el modelo lo arma [comprobante_service.texto_para_ia](../../app/services/comprobante_service.py:64): antepone los campos ya normalizados del comprobante (tipo, serie-número, contraparte, fecha, montos) al JSON crudo del SIRE (`extra.raw_sire`) y, si existe, al detalle de ítems extraído por scraping (`detalle_sunat` — ver [flujo de extracción de detalle](04-extraccion-detalle.md)).

## Selección de pendientes

[listar_pendientes_analisis](../../app/repositories/comprobantes.py:147) selecciona los comprobantes cuyo `estado_procesamiento` sea `sire_recibido`, `error_analisis`, o esté ausente — es decir, el sistema reintenta automáticamente lo que falló en una corrida anterior. Un comprobante sin `extra.raw_sire` ni `detalle_sunat` se marca directamente `sin_datos` sin llamar a Gemini.

Todos los comprobantes pendientes se procesan en paralelo con `asyncio.gather`, cada llamada al modelo despachada a un hilo (`asyncio.to_thread`) porque el SDK de Gemini usado aquí es síncrono.

Al terminar, cada comprobante queda en `analizado`, `error_analisis` o `sin_datos` según el resultado, y la respuesta agrega los conteos (`procesadas`, `errores`, `sin_datos`) sobre el total de pendientes encontrados.
