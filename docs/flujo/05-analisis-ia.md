# Flujo — Análisis con IA

El endpoint [ejecutar_analisis](../endpoints/analysis.md) llama a [procesar_lote_extracciones](../../app/services/analisis_ia.py:246).

## RAG de dos niveles

1. **Base global (normativa contable).** Cargada una sola vez en memoria al arrancar el servidor, mediante [cargar_vector](../../app/services/analisis_ia.py:28), leyendo la colección de embeddings globales durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación. Representa normativa contable estándar (el Plan Contable General Empresarial).

2. **RAG de usuario**, resuelto en el propio router del endpoint de análisis, no en el servicio, con el siguiente orden de prioridad: primero, los PDFs adjuntados en la misma petición de análisis, que se procesan en memoria y no se persisten; si no se adjuntan, se usan los fragmentos previamente indexados en la colección de embeddings por usuario, subidos con anterioridad mediante el endpoint de subida de referencias (ver [endpoints — References](../endpoints/references.md)).

## Detalles del proceso

El cliente de Gemini, en [_get_client](../../app/services/analisis_ia.py:21), se construye de forma perezosa, en el primer uso, no al importar el módulo. Así, si falta la variable de entorno de la API key de Gemini, solo falla la llamada que efectivamente necesita el modelo, en vez de impedir que se cargue todo el paquete de rutas al arrancar la aplicación.

[buscar_contexto](../../app/services/analisis_ia.py:111) genera el embedding del texto de la factura y calcula la similitud de coseno contra cada elemento de la base global y de la base del usuario, en memoria, devolviendo los veinte resultados más relevantes de cada fuente como texto plano de contexto. Esta búsqueda ocurre completamente en memoria, no con un índice vectorial de la base de datos — ver la limitación de escalabilidad señalada en [ciclo de vida](../arquitectura/ciclo-de-vida.md).

[extraer_datos_factura](../../app/services/analisis_ia.py:170) arma un prompt con reglas de negocio explícitas (la serie F corresponde a una factura de bienes o servicios, la serie E a honorarios o servicios profesionales), el contexto normativo recuperado, y le pide al modelo de Gemini —configurado para responder en formato JSON— un resultado con el detalle de líneas (producto, categoría contable, cantidad, importe y razón), la cuenta contable, el centro de costos, la condición de IGV, el resultado de la clasificación (costo, gasto, activo o no determinado), el nivel de confianza de la IA, su estado, una descripción y observaciones.

Si la factura tiene detalle de compras de SUNAT (obtenido por el scraping opcional, ver [flujo de scraping de detalle](04-scraping-detalle.md)), ese detalle real se concatena al texto enviado al modelo para enriquecer la clasificación.

Se seleccionan como pendientes las facturas cuyo estado de procesamiento sea "recibida de SIRE", "error de análisis", o esté ausente o vacío — es decir, el sistema reintenta automáticamente las facturas que fallaron en una corrida anterior.

Como defensa adicional a la deduplicación global que corre en el arranque del servidor (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)), este proceso también deduplica por número de serie dentro del propio lote que está procesando, para no analizar dos veces —y gastar cuota de la API de Gemini innecesariamente— el mismo comprobante si hubiera duplicados históricos.

Todas las facturas pendientes se procesan en paralelo, cada una en un hilo separado, porque la librería de Gemini usada aquí es síncrona.

Al terminar, el estado de procesamiento de cada factura se actualiza a analizada, a error de análisis, o a sin datos, según el resultado obtenido.
