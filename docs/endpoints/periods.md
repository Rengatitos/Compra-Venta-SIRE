# Endpoints — Periods

Prefijo `/sol-users/{user_id}/periodos`, montado en [main.py](../../app/main.py:112). Router en [periods.py](../../app/api/routes/periods.py).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/{user_id}/periodos/` | [create_period](../../app/api/routes/periods.py:11) | require_same_user |
| GET | `/sol-users/{user_id}/periodos/` | [list_periods](../../app/api/routes/periods.py:28) | require_same_user |
| GET | `/sol-users/{user_id}/periodos/{periodo}` | [get_period](../../app/api/routes/periods.py:34) | require_same_user |
| PUT | `/sol-users/{user_id}/periodos/{periodo}` | [update_period](../../app/api/routes/periods.py:42) | require_same_user |
| DELETE | `/sol-users/{user_id}/periodos/{periodo}` | [delete_period](../../app/api/routes/periods.py:59) | require_same_user |

**create_period** crea un periodo fiscal nuevo en estado pendiente; falla si ya existe uno igual para ese usuario. El formato del periodo y su unicidad se explican en [flujo de creación de periodo](../flujo/02-periodos.md) y en [modelo de datos de periodos](../modelo-datos/periodos.md).

**list_periods** lista hasta 100 periodos del usuario.

**get_period** devuelve el detalle de un periodo puntual.

**update_period** actualiza el estado del periodo.

**delete_period** borra el periodo y todas las facturas asociadas a él.
