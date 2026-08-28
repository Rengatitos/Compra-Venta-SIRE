# Autenticación

El sistema usa un JWT propio (HS256 por defecto), sin OAuth de usuario final: el token identifica una **empresa** (un RUC ante SUNAT), no una persona.

## Emisión del token

[POST /api/v1/auth/login](../endpoints/empresas.md) recibe RUC, usuario SOL y contraseña. [login](../../app/api/v1/routes/auth.py:15) busca la empresa por RUC, descifra la contraseña almacenada (ver [cifrado](cifrado.md)) y la compara en texto plano contra la recibida. Si coincide, [create_token](../../app/core/auth.py:19) firma un payload con `empresa_id`, `ruc` y una expiración de `JWT_EXPIRE_HOURS` horas (default 2).

## Verificación del token

[decode_token](../../app/core/auth.py:29) decodifica y valida la firma y la expiración, devolviendo `401` con un mensaje explícito en cada caso de fallo (`Token expirado`, `Token inválido`).

## Dependencias de autorización

| Dependencia | Uso | Comportamiento |
|---|---|---|
| [empresa_autenticada](../../app/core/auth.py:52) | Endpoints que no cuelgan de `/empresas/{ruc}` (jobs, analytics, temas base) | Decodifica el token y busca la empresa por `empresa_id`. `401` si no hay token, el `empresa_id` falta o la empresa no existe. |
| [empresa_actual](../../app/api/v1/deps.py:9) | Casi todos los endpoints bajo `/empresas/{ruc}/...` | Además de `empresa_autenticada`, verifica que el RUC del path coincida con el del token. `403` si no coincide. |
| [empresa_id](../../app/api/v1/deps.py:22) | Endpoints que solo necesitan el identificador, no el documento completo | Envuelve `empresa_actual` y devuelve `str(empresa["_id"])`. |
| [verify_admin](../../app/core/auth.py:44) | Endpoints administrativos (p. ej. listar todas las empresas) | Compara el header `X-Admin-Token` contra `ADMIN_TOKEN`. No usa JWT. |

`empresa_actual` es la pieza central del modelo de autorización: **el sujeto nunca sale del path**, sale del token. Esto reemplaza un diseño anterior donde la identidad viajaba por separado en el path y en parámetros de query, lo que permitía que ambos se contradijeran.

## Analytics y jobs

Los endpoints de `/api/v1/analytics/*` usan una dependencia propia, [token_dashboard](../../app/api/v1/routes/analytics.py:14), que solo decodifica el token sin resolver la empresa contra Mongo — porque esos endpoints reciben una lista de RUCs por query param (`rucs`) y agregan datos de varias empresas a la vez.

Los endpoints de `/api/v1/jobs/{job_id}` usan `empresa_autenticada` y comprueban la pertenencia comparando `job.ruc` contra el RUC del token, porque un job no cuelga de `/empresas/{ruc}` en su path.
