# Endpoints — Analytics

Prefijo `/analytics`, montado en [main.py](../../app/main.py:137). Router en [analytics.py](../../app/api/routes/analytics.py). Pensado para ser consumido por un sistema externo de contabilidad que agrega datos de varios RUCs o usuarios SOL a la vez.

## Modelo de autorización distinto al resto de la API

Todos los endpoints de este router usan [verify_dashboard_token](../../app/api/routes/analytics.py:15) en vez de las dependencias habituales. Esta dependencia solo decodifica el token, sin verificar que el usuario exista en la base ni exigir que sea "el mismo usuario" — el filtrado real de a qué usuarios se puede acceder ocurre a través del parámetro de RUCs (una lista separada por comas), no a través del identificador embebido en el token. La función [get_target_user_ids](../../app/services/analytics_service.py:15), que resuelve esos RUCs a identificadores de usuario, documenta explícitamente en su propio código el razonamiento: el token global ya está verificado, así que el servicio confía en los RUCs que el sistema que llama (quien a su vez recibió la llamada del frontend) le pasa. Es decir, la autorización fina de "qué RUCs puede ver este llamador" se delega por completo al sistema externo, y no se revalida en esta API. Ver también [autenticación](../arquitectura/autenticacion.md).

## Endpoints

| Método | Path completo | Función |
|---|---|---|
| GET | `/analytics/summary` | [get_summary](../../app/api/routes/analytics.py:23) |
| GET | `/analytics/top-suppliers` | [get_top_suppliers](../../app/api/routes/analytics.py:34) |
| GET | `/analytics/ai-classification` | [get_ai_classification](../../app/api/routes/analytics.py:46) |
| GET | `/analytics/invoices-by-day` | [get_invoices_by_day](../../app/api/routes/analytics.py:57) |
| GET | `/analytics/periodos` | [get_available_periodos](../../app/api/routes/analytics.py:68) |
| GET | `/analytics/dashboard-data` | [get_dashboard_data](../../app/api/routes/analytics.py:82) |

Todos requieren verify_dashboard_token.

**get_summary** devuelve totales de facturas, monto e IGV, junto con el conteo de facturas procesadas y pendientes, para los RUCs y el periodo dados.

**get_top_suppliers** devuelve el ranking de proveedores por monto total, con un límite configurable (5 por defecto).

**get_ai_classification** devuelve el conteo de facturas agrupado por el resultado de la clasificación de la IA, agrupado en las categorías de gasto, costo, mixto y otros.

**get_invoices_by_day** devuelve la cantidad de facturas por día del mes, extraído de la fecha de emisión de cada comprobante.

**get_available_periodos** lista los periodos que tienen facturas para los RUCs dados, en orden descendente.

**get_dashboard_data** combina en paralelo los cuatro endpoints anteriores más una lista de hasta 200 facturas, para poblar un dashboard completo en una sola llamada. La agregación se hace con ejecución concurrente de las distintas consultas.

Todos los endpoints de este router aceptan un parámetro de tipo de operación, con un valor de compras por defecto, para filtrar por el tipo de operación registrado en cada factura — ver la nota al respecto en [modelo de datos de facturas](../modelo-datos/facturas.md).
