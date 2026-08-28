# Endpoints — Periodos

Todos bajo `/api/v1/empresas/{ruc}/periodos`, protegidos por [empresa_id](../../app/api/v1/deps.py:22) (el RUC del path debe coincidir con el del token).

## `POST /api/v1/empresas/{ruc}/periodos`

[crear_periodo](../../app/api/v1/routes/periodos.py:14). Body `PeriodoCreate` con `periodo` en formato `YYYYMM` (validado por [domain/periodo.py](../../app/domain/periodo.py)). `409` si ya existe para esa empresa.

## `GET /api/v1/empresas/{ruc}/periodos`

[listar_periodos](../../app/api/v1/routes/periodos.py:27). Todos los periodos de la empresa.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}`

[obtener_periodo](../../app/api/v1/routes/periodos.py:33). `404` si no existe.

## `PUT /api/v1/empresas/{ruc}/periodos/{periodo}`

[actualizar_periodo](../../app/api/v1/routes/periodos.py:44). Cambia el `estado` del periodo directamente. Los valores de `estado` que el propio sistema escribe automáticamente son `sincronizado` (tras una sincronización exitosa) y `sin_propuesta` (cuando SUNAT no tiene propuesta para ese periodo) — ver [propuesta_service.py](../../app/services/propuesta_service.py).

## `DELETE /api/v1/empresas/{ruc}/periodos/{periodo}`

[eliminar_periodo](../../app/api/v1/routes/periodos.py:61). Borra también todos los comprobantes de ese periodo antes de borrar el periodo. `404` si el periodo no existe.

Ver también [flujo de creación de periodo](../flujo/02-periodos.md).
