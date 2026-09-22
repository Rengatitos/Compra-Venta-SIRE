# Modelo de datos — Índices creados en el arranque

Todos estos índices se crean durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación, en [main.py](../../app/main.py), uno por repositorio. Si la creación falla, se registra la excepción pero el servicio sigue arrancando.

| Colección | Índice | Repositorio |
|---|---|---|
| `empresas` | único sobre `ruc` | [empresas.crear_indices](../../app/repositories/empresas.py) |
| `periodos` | único sobre `(empresa_id, periodo)` | [periodos.crear_indices](../../app/repositories/periodos.py) |
| `comprobantes` | `(empresa_id, periodo)`; único (`uniq_comprobante`) sobre `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)` | [comprobantes.crear_indices](../../app/repositories/comprobantes.py) |
| `jobs` | único sobre `job_id`; `(ruc, periodo)` | [jobs.crear_indices](../../app/repositories/jobs.py) |
| `comprobantes_externos` | único `(empresa_id, id_externo)`; únicos parciales `(empresa_id, fuente, nro_operacion)` y `(empresa_id, libro, tipo_cp, serie, numero)`; `(empresa_id, libro, periodo, creado_en)` | [comprobantes_externos.crear_indices](../../app/repositories/comprobantes_externos.py) |
| `codigos_vinculacion` | TTL sobre `expira_en`; único `(ruc, codigo_hash)` | [codigos_vinculacion.crear_indices](../../app/repositories/codigos_vinculacion.py) |

Ver [modelo de datos — comprobantes](comprobantes.md) para el detalle de por qué `uniq_comprobante` es la pieza que hace innecesaria una rutina de deduplicación en el arranque.
