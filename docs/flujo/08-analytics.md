# Flujo — Analytics

El servicio de analytics ejecuta agregaciones de Mongo sobre la colección `comprobantes`, filtrando siempre por una lista de `empresa_id` resuelta a partir de RUCs mediante [get_target_empresa_ids](../../app/services/analytics_service.py), lo que permite consultas multi-empresa desde un sistema externo.

[build_match_filter](../../app/services/analytics_service.py) construye el filtro común (empresas, periodo y `libro`) que reutilizan las distintas funciones de agregación: [get_summary](../../app/services/analytics_service.py), [get_top_contrapartes](../../app/services/analytics_service.py), [get_comprobantes_by_day](../../app/services/analytics_service.py) y [get_comprobantes_list](../../app/services/analytics_service.py). Los montos que devuelven estas agregaciones se convierten de `Decimal128` a `float` con [monto_a_float](../../app/repositories/_mongo.py), porque `Decimal128` no es serializable a JSON.

El conteo por día ([get_comprobantes_by_day](../../app/services/analytics_service.py)) agrupa con el operador `$dayOfMonth` de Mongo directamente sobre `fecha_emision`, que es un campo `date` real — no hay que parsear texto para agrupar por fecha.

Ver [endpoints — Analytics](../endpoints/analytics.md) para el detalle de cada endpoint HTTP y la nota sobre su modelo de autorización, que es distinto del resto de la API: el token solo se decodifica con [token_dashboard](../../app/api/v1/routes/analytics.py), sin resolver la empresa contra Mongo, y la restricción de acceso por RUC se delega al sistema externo que llama.
