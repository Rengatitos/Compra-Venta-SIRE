# Ciclo de vida de la aplicación

Gestionado por el `lifespan` de FastAPI en [main.py](../../app/main.py:42).

## Arranque

1. Se configura logging a consola y a archivo (`logs/automat_api.log`), silenciando los loggers ruidosos de `httpx` y `google_genai`.
2. [connect_to_mongo](../../app/db/database.py:16) crea el cliente de Motor y resuelve la base según `MONGO_URI` / `MONGO_FACTURASDB_NAME`.
3. Se crean los índices de cada colección, uno por repositorio: `empresas` (RUC único), `periodos` (empresa+periodo único), `comprobantes` (índice de consulta por empresa+periodo, más el índice único `uniq_comprobante` sobre la clave de identidad del comprobante), `jobs` (`job_id` único, más consulta por RUC+periodo) y `vector_global`/`vector_usuarios`. Si la creación de índices falla, se registra el error pero **el servicio sigue arrancando** — no es un fallo fatal.
4. [cargar_vector](../../app/services/analisis_ia.py:28) trae a memoria todos los chunks de la colección `vector_global` (la base normativa compartida, no la de cada empresa), para que la búsqueda de contexto del análisis IA no dependa de una consulta a Mongo por cada factura.

## Apagado

[close_mongo_connection](../../app/db/database.py:22) cierra el cliente de Motor y limpia las variables globales de conexión.

## Nota sobre el índice único de comprobantes

El índice `uniq_comprobante` (empresa, periodo, libro, origen, tipo_cp, serie, numero) es lo que reemplaza la deduplicación manual que antes corría en cada arranque: al ser un upsert sobre una clave con restricción única, un comprobante duplicado nunca llega a insertarse dos veces.
