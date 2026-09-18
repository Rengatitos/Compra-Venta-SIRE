# Modelo de datos — Índices creados en el arranque

Todos estos índices se crean durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación, en [main.py](../../app/main.py), uno por repositorio. Si la creación falla, se registra la excepción pero el servicio sigue arrancando.

| Colección | Índice | Repositorio |
|---|---|---|
| `empresas` | único sobre `ruc` | [empresas.crear_indices](../../app/repositories/empresas.py) |
| `periodos` | único sobre `(empresa_id, periodo)` | [periodos.crear_indices](../../app/repositories/periodos.py) |
| `comprobantes` | `(empresa_id, periodo)`; único (`uniq_comprobante`) sobre `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)` | [comprobantes.crear_indices](../../app/repositories/comprobantes.py) |
| `jobs` | único sobre `job_id`; `(ruc, periodo)` | [jobs.crear_indices](../../app/repositories/jobs.py) |

Ver [modelo de datos — comprobantes](comprobantes.md) para el detalle de por qué `uniq_comprobante` es la pieza que hace innecesaria una rutina de deduplicación en el arranque.
