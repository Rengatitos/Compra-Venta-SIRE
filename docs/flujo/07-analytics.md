# Flujo — Analytics

El servicio de analytics ejecuta agregaciones de Mongo sobre la colección `comprobantes`, filtrando siempre por una lista de `empresa_id` resuelta a partir de RUCs mediante [get_target_empresa_ids](../../app/services/analytics_service.py:44), lo que permite consultas multi-empresa desde un sistema externo.

[build_match_filter](../../app/services/analytics_service.py:29) construye el filtro común (empresas, periodo y `libro`) que reutilizan las distintas funciones de agregación: [get_summary](../../app/services/analytics_service.py:56), [get_top_contrapartes](../../app/services/analytics_service.py:105), [get_ai_classification](../../app/services/analytics_service.py:127), [get_comprobantes_by_day](../../app/services/analytics_service.py:154) y [get_comprobantes_list](../../app/services/analytics_service.py:168). Los montos que devuelven estas agregaciones se convierten de `Decimal128` a `float` con [monto_a_float](../../app/repositories/_mongo.py:32), porque `Decimal128` no es serializable a JSON.

El conteo por día ([get_comprobantes_by_day](../../app/services/analytics_service.py:154)) agrupa con el operador `$dayOfMonth` de Mongo directamente sobre `fecha_emision`, que es un campo `date` real — no hay que parsear texto para agrupar por fecha.

Ver [endpoints — Analytics](../endpoints/analytics.md) para el detalle de cada endpoint HTTP y la nota sobre su modelo de autorización, que es distinto del resto de la API: el token solo se decodifica con [token_dashboard](../../app/api/v1/routes/analytics.py:14), sin resolver la empresa contra Mongo, y la restricción de acceso por RUC se delega al sistema externo que llama.
