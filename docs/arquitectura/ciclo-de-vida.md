# Ciclo de vida de la aplicación

Gestionado por el `lifespan` de FastAPI en [main.py](../../app/main.py).

## Arranque

1. Se configura logging a consola y a archivo (`logs/automat_api.log`), silenciando el logger de `httpx`, que es ruidoso a nivel INFO.
2. `connect_to_mongo` ([database.py](../../app/db/database.py)) crea el cliente de Motor y resuelve la base según `MONGO_URI` / `MONGO_FACTURASDB_NAME`.
3. Se crean los índices de cada colección, uno por repositorio: `empresas` (RUC único), `periodos` (empresa+periodo único), `comprobantes` (índice de consulta por empresa+periodo, más el índice único `uniq_comprobante` sobre la clave de identidad del comprobante), `jobs` (`job_id` único, más consulta por RUC+periodo) y `plan_cuentas` (empresa+código). Si la creación de índices falla, se registra el error pero **el servicio sigue arrancando** — no es un fallo fatal.
4. Se dan por fallidos los jobs de clasificación y de historial SIRE que quedaron vivos y **no** son de la cola durable.
5. Arranca el worker de la [cola durable](cola.md) (salvo `COLA_HABILITADA=false`), que primero devuelve a la cola lo que el reinicio dejó a medias.

## Apagado

Se detiene el worker de la cola: un job cortado queda en progreso con el latido viejo y vuelve a la cola al siguiente arranque. Después, `close_mongo_connection` cierra el cliente de Motor y limpia las variables globales de conexión.

## Nota sobre el índice único de comprobantes

El índice `uniq_comprobante` (empresa, periodo, libro, origen, tipo_cp, serie, numero) es lo que reemplaza la deduplicación manual que antes corría en cada arranque: al ser un upsert sobre una clave con restricción única, un comprobante duplicado nunca llega a insertarse dos veces.

## Recarga en desarrollo

`make back` arranca Uvicorn con `--reload`, que vigila todos los `.py` del repositorio, incluidos `tests/`. Los trabajos de scraping viven en un hilo del mismo proceso: editar cualquier `.py` mientras uno corre reinicia el servidor, el navegador muere («Target page, context or browser has been closed») y el job termina «completado» con cero detalles. Antes de lanzar una extracción real, dejar hechas todas las ediciones y no tocar código hasta que el job termine.
