# Modelo de datos — jobs

Un trabajo asíncrono y su estado observable. Contrato definido en [domain/jobs.py](../../app/domain/jobs.py), persistido por [repositories/jobs.py](../../app/repositories/jobs.py). Quién los ejecuta: la [cola durable](../arquitectura/cola.md).

| Campo | Tipo | Descripción |
|---|---|---|
| `job_id` | str | `uuid4().hex`. Único — índice único. Es el identificador expuesto en la API, no el `_id` de Mongo. |
| `tipo` | str | `TipoJob`: ver la tabla de [endpoints de jobs](../endpoints/jobs.md). |
| `estado` | str | `pendiente` → `en_progreso` → `completado` \| `fallido`. Un reintento vuelve a `pendiente`. |
| `ruc`, `periodo`, `libro` | str, str, str \| None | Contexto de negocio. `ruc` y `periodo` van vacíos en el empaquetado y el correo, que son de una solicitud entera. |
| `progreso` | dict | `{actual, total, mensaje}`. `porcentaje` se calcula al vuelo, no se persiste. |
| `resultado` | dict \| None | Payload libre devuelto por la tarea al completarse. |
| `error` | str \| None | Mensaje del último fallo. |
| `creado_en`, `actualizado_en` | datetime UTC | |
| `gestionado` | bool | Lo ejecuta la cola. `false` en los de historial y en los de antes de la cola. |
| `cola` | str \| None | Carril de exclusión: el RUC, `sire:{RUC}`, `clasificador` o `correo`. |
| `parametros` | dict | Lo que el manejador necesita además del contexto (p. ej. `hasta_terminar`, `reclasificar`, `carga_id`). Nunca contraseñas. |
| `solicitud_id` | str \| None | Solicitud de procesamiento masivo a la que pertenece el paso. |
| `intentos`, `max_intentos` | int | Intentos hechos y tope (`COLA_MAX_INTENTOS`). |
| `ultimo_intento_en`, `siguiente_intento_en` | datetime UTC \| None | Cuándo empezó el último intento y cuándo toca el siguiente. |
| `latido_en` | datetime UTC \| None | Lo actualiza el worker mientras corre; si vence, el job se da por interrumpido. |
| `historial_errores` | list | `{intento, en, error}` por cada intento fallido. |

Índices: único sobre `job_id`; `(ruc, periodo)`; `(ruc, creado_en desc)` para el historial de [`GET /api/v1/jobs`](../endpoints/jobs.md); `(gestionado, estado, creado_en)` para la toma del worker; `solicitud_id` (sparse) para los pasos de una solicitud.
