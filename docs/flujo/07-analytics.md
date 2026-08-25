# Flujo — Analytics

El servicio de analytics ejecuta agregaciones de Mongo (con etapas de filtrado y agrupamiento) sobre la colección de facturas, filtrando siempre por una lista de identificadores de usuario resuelta a partir de RUCs mediante [get_target_user_ids](../../app/services/analytics_service.py:15), lo que permite soportar consultas multi-empresa desde un sistema externo.

[build_match_filter](../../app/services/analytics_service.py:4) construye el filtro común (usuarios, periodo y tipo de operación) que reutilizan las distintas funciones de agregación: [get_summary](../../app/services/analytics_service.py:29), [get_top_suppliers](../../app/services/analytics_service.py:75), [get_ai_classification](../../app/services/analytics_service.py:98), [get_invoices_by_day](../../app/services/analytics_service.py:132) y [get_invoices_list](../../app/services/analytics_service.py:159).

Ver [endpoints — Analytics](../endpoints/analytics.md) para el detalle de cada endpoint HTTP y la nota sobre su modelo de autorización, que es distinto del resto de la API: el token solo se decodifica, sin validarse contra la base de usuarios, y la restricción de acceso por RUC se delega por completo al sistema que llama.
