# Endpoints — Analytics

Todos bajo `/api/v1/analytics`, pensados para ser consumidos por un sistema externo de contabilidad que consulta varias empresas a la vez. Se autentican con el mismo JWT, pero vía [token_dashboard](../../app/api/v1/routes/analytics.py:14), que solo decodifica el token sin resolver la empresa contra Mongo.

Todos aceptan `rucs` (opcional, RUCs separados por comas — sin él, el filtro de empresa queda vacío y las agregaciones no devuelven nada), `periodo` y `libro` (default `compras`).

| Endpoint | Servicio |
|---|---|
| `GET /summary` | [get_summary](../../app/services/analytics_service.py) — total de comprobantes, monto total, IGV total, cuántos están procesados vs. pendientes de análisis. |
| `GET /top-contrapartes` | [get_top_contrapartes](../../app/services/analytics_service.py) — contrapartes con mayor monto acumulado. Query param adicional `limit` (default 5). |
| `GET /ai-classification` | [get_ai_classification](../../app/services/analytics_service.py) — distribución de comprobantes por resultado de la IA (`GASTO`, `COSTO`, `MIXTO`, `OTROS`). |
| `GET /comprobantes-por-dia` | [get_comprobantes_by_day](../../app/services/analytics_service.py) — conteo de comprobantes agrupado por día del mes, usando `$dayOfMonth` sobre `fecha_emision` (un campo `date` real, no texto). |
| `GET /periodos` | [periodos_disponibles](../../app/services/analytics_service.py) — periodos con datos, para las empresas indicadas. |
| `GET /dashboard-data` | Ejecuta las cinco consultas anteriores en paralelo (`asyncio.gather`) y las devuelve en un solo payload, más el listado de comprobantes del periodo. |

Ver también [flujo de analytics](../flujo/07-analytics.md).
