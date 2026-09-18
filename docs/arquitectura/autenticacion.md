# Autenticación

El acceso al panel es una **cuenta de Google**, y el JWT propio (HS256 por defecto) identifica a una **persona**, no a una empresa. Quien entra ve y opera todas las empresas registradas, y cambia de una a otra sin volver a autenticarse.

Hasta septiembre de 2026 el token identificaba una empresa (un RUC ante SUNAT) y se emitía a partir de sus credenciales SOL. Esas credenciales siguen guardadas y cifradas en cada empresa —el OAuth de la API SIRE y el scraping del portal las necesitan en claro, ver [cifrado](cifrado.md)— pero ya no sirven para entrar.

## Emisión del token

1. El navegador hace todo el intercambio con Google (Google Identity Services) y obtiene un **ID token** firmado.
2. [POST /api/v1/auth/google](../endpoints/empresas.md) recibe ese token en `credential`.
3. [verificar_id_token](../../app/services/google_oauth.py) comprueba la firma RS256 contra el JWKS de Google, la audiencia (`aud` == `GOOGLE_CLIENT_ID`), el emisor, la expiración y que el correo esté verificado.
4. [login_google](../../app/api/v1/routes/auth.py) contrasta el correo con `GOOGLE_ALLOWED_EMAILS` y, si pasa, [create_token](../../app/core/auth.py) firma un payload con `tipo`, `sub`, `email` y una expiración de `JWT_EXPIRE_HOURS` horas (default 2).

El backend nunca habla con Google salvo para descargar sus claves públicas, así que no custodia ningún `client_secret` ni necesita un `redirect_uri` por entorno. Esa descarga es bloqueante y va a un hilo con `asyncio.to_thread`: la API corre con un solo worker y una llamada síncrona la congelaría entera.

| Situación | Respuesta |
|---|---|
| ID token inválido, expirado o con el correo sin verificar | `401` |
| Correo auténtico pero fuera de la allowlist | `403` |
| No se pudo contactar con el JWKS de Google | `503` |
| `GOOGLE_CLIENT_ID` sin configurar | `500` |

El `503` está separado del `401` a propósito: una caída de Google no es un token falso, y confundirlos haría buscar el problema en el sitio equivocado.

## Verificación del token

[decode_token](../../app/core/auth.py) valida firma y expiración, devolviendo `401` con un mensaje explícito en cada caso (`Token expirado`, `Token inválido`).

## Dependencias de autorización

| Dependencia | Uso | Comportamiento |
|---|---|---|
| [usuario_actual](../../app/core/auth.py) | Todo lo autenticado | Decodifica el token, exige `tipo == "usuario"` y `email`, y revalida la allowlist. `401` sin token, con un token del esquema anterior o sin correo; `403` si el correo ya no está autorizado. No toca Mongo. |
| [empresa_actual](../../app/api/v1/deps.py) | Casi todos los endpoints bajo `/empresas/{ruc}/...` | Exige sesión y resuelve la empresa **por el RUC del path**. `404` si no existe ninguna con ese RUC. |
| [empresa_id](../../app/api/v1/deps.py) | Endpoints que solo necesitan el identificador | Envuelve `empresa_actual` y devuelve `str(empresa["_id"])`. |

El modelo de autorización se puede resumir así: **el permiso sale del token y el objeto sale del path**. La regla anterior —«el sujeto nunca sale del path»— sigue viva, solo que el sujeto ya no es la empresa sino la persona, y la empresa pasó a ser aquello sobre lo que actúa. Como el permiso es total sobre todas las empresas registradas, aceptar el RUC del path no abre ninguna vía de escalada.

La allowlist se revalida **en cada petición** y no solo al iniciar sesión: así, quitar un correo de `GOOGLE_ALLOWED_EMAILS` y reiniciar lo expulsa en el acto en lugar de dejarlo dentro hasta que caduque su token.

## Invalidar las sesiones del esquema anterior

Lo hace el claim `tipo`: un token viejo no lo lleva y cae con un `401` que nombra el motivo.

**No hay que rotar `JWT_SECRET_KEY` para esto.** [encryption.py](../../app/core/encryption.py) usa `SOL_USER_CRYPTO_KEY or JWT_SECRET_KEY` como semilla de Fernet, así que en cualquier despliegue sin la primera definida, cambiar el secreto del JWT dejaría **ilegibles todas las contraseñas SOL guardadas** y tumbaría el scraping, las detracciones y la renovación del token de SUNAT — con el síntoma apareciendo horas después, lejos del cambio.

## Analytics y jobs

Los endpoints de `/api/v1/analytics/*` y `/api/v1/jobs` no cuelgan de `/empresas/{ruc}`, así que usan `usuario_actual` directamente y reciben el RUC (o la lista de RUCs) por query param. Antes eso habría sido una vía para leer datos de otra empresa; con una sesión por persona no revela nada que la misma sesión no pueda pedir por `GET /empresas`. De los RUCs recibidos solo se comprueba que existan.

## Alcance de una sesión

Una sesión válida puede hacer **todo** sobre cualquier empresa, incluido `DELETE /empresas/{ruc}`, que borra en cascada sus comprobantes, periodos y plan de cuentas. Con un único correo autorizado el riesgo es bajo; al ampliar la allowlist hará falta un modelo de roles.
