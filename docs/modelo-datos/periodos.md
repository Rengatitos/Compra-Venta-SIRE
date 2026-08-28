# Modelo de datos — periodos

Un periodo fiscal de sincronización SIRE para una empresa. Poblada por [crear_periodo](../../app/api/v1/routes/periodos.py:14).

| Campo | Tipo | Descripción |
|---|---|---|
| `empresa_id` | str | `_id` de la empresa dueña, como cadena. |
| `periodo` | str | Formato `YYYYMM`, validado por [domain/periodo.py](../../app/domain/periodo.py). |
| `estado` | str | `pendiente` al crearse; `sincronizado` cuando la sincronización de la propuesta SIRE completa el proceso con éxito; `sin_propuesta` cuando SUNAT no tiene propuesta para ese periodo. Ver [flujo de sincronización](../flujo/03-sincronizacion-propuesta.md). También puede establecerse manualmente vía `PUT`. |
| `fecha_creacion` | str, ISO con zona horaria UTC | |

Índice: único compuesto por `(empresa_id, periodo)`.
