# Modelo de datos — jobs

Un trabajo asíncrono y su estado observable. Contrato definido en [domain/jobs.py](../../app/domain/jobs.py), persistido por [repositories/jobs.py](../../app/repositories/jobs.py).

| Campo | Tipo | Descripción |
|---|---|---|
| `job_id` | str | `uuid4().hex`. Único — índice único. Es el identificador expuesto en la API, no el `_id` de Mongo. |
| `tipo` | str | Hoy el único valor es `extraccion_detalles` (ver [domain/jobs.py — TipoJob](../../app/domain/jobs.py)). El contrato está pensado para extenderse a otras operaciones asíncronas sin cambiar la forma del documento. |
| `estado` | str | `pendiente` → `en_progreso` → `completado` \| `fallido`. |
| `ruc`, `periodo`, `libro` | str, str, str \| None | Contexto de negocio del job. `libro` es opcional porque no todos los tipos de job están atados a un libro. |
| `progreso` | dict | `{actual, total, mensaje}`. `porcentaje` se calcula al vuelo, no se persiste. |
| `resultado` | dict \| None | Payload libre devuelto por la tarea al completarse. |
| `error` | str \| None | Mensaje de la excepción, si el job terminó en `fallido`. |
| `creado_en`, `actualizado_en` | datetime UTC | |

Índices: único sobre `job_id`; compuesto sobre `(ruc, periodo)` para consultas por contexto de negocio; compuesto sobre `(ruc, creado_en desc)` para el historial que lista [`GET /api/v1/jobs`](../endpoints/jobs.md).
