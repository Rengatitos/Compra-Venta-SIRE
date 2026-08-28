# Modelo de datos — Índices creados en el arranque

Todos estos índices se crean durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación, en [main.py](../../app/main.py:48), uno por repositorio. Si la creación falla, se registra la excepción pero el servicio sigue arrancando.

| Colección | Índice | Repositorio |
|---|---|---|
| `empresas` | único sobre `ruc` | [empresas.crear_indices](../../app/repositories/empresas.py:16) |
| `periodos` | único sobre `(empresa_id, periodo)` | [periodos.crear_indices](../../app/repositories/periodos.py:15) |
| `comprobantes` | `(empresa_id, periodo)`; único (`uniq_comprobante`) sobre `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)` | [comprobantes.crear_indices](../../app/repositories/comprobantes.py:35) |
| `jobs` | único sobre `job_id`; `(ruc, periodo)` | [jobs.crear_indices](../../app/repositories/jobs.py:15) |
| `vector_global` | `metadata.documento` | [vectores.crear_indices](../../app/repositories/vectores.py:22) |
| `vector_usuarios` | `(empresa_id, metadata.documento)` | [vectores.crear_indices](../../app/repositories/vectores.py:22) |

Ver [modelo de datos — comprobantes](comprobantes.md) para el detalle de por qué `uniq_comprobante` es la pieza que hace innecesaria una rutina de deduplicación en el arranque.
