# Autenticación y cifrado

Todo el código relevante está en `app/core/auth.py` y `app/core/encryption.py`.

## JWT (`app/core/auth.py`)

No hay usuarios "persona"; el JWT identifica un **usuario SOL** (una empresa/RUC registrada en el sistema, documento de la colección `sol_users`).

- `create_token(user_id: str, ruc: str) -> str`: firma con `jwt.encode` un payload `{"user_id": ..., "ruc": ..., "exp": now_utc + JWT_EXPIRE_HOURS}` usando `JWT_SECRET_KEY`/`JWT_ALGORITHM` (`HS256` por defecto). Se emite únicamente en `POST /sol-users/login`.
- `decode_token(token: str) -> dict`: decodifica y valida firma+expiración. Lanza `HTTPException(401, "Token expirado")` o `HTTPException(401, "Token inválido")` según el tipo de error de PyJWT.
- `verify_user(credentials, db) -> dict`: dependencia de FastAPI (usa `HTTPBearer`). Exige el header `Authorization: Bearer <token>`, decodifica, extrae `user_id`, lo convierte a `ObjectId` (400/401 si no es válido) y busca el documento en `sol_users`. Si el usuario ya no existe (fue borrado después de emitirse el token), retorna 401 "Usuario no encontrado" — es decir, el JWT por sí solo no basta, siempre se revalida contra la base en cada request.
- `require_same_user(user_id: str, user=Depends(verify_user)) -> dict`: dependencia compuesta que además compara `str(user["_id"])` contra el `user_id` recibido en el path de la ruta, devolviendo 403 si no coinciden. Es la forma estándar de proteger rutas anidadas bajo `/sol-users/{user_id}/...` (periods, invoices, references, analysis) para que un usuario autenticado no pueda leer/modificar datos de otro `user_id` simplemente cambiando el path. Se creó para eliminar una comprobación `if str(user["_id"]) != user_id: raise HTTPException(403, ...)` que estaba duplicada literalmente en varios routers.
- `verify_admin(api_key=Security(api_key_header))`: dependencia separada, **no basada en JWT**. Usa un `APIKeyHeader` llamado `X-Admin-Token` comparado directamente contra la variable de entorno `ADMIN_TOKEN`. Se usa en endpoints de administración: `GET /sol-users/` (listar todos) y `DELETE /sol-users/cleanup/{tenant_id}/{cliente_id}/{cuenta_id}` (borrado masivo).
- `verify_dashboard_token` (definida en `app/api/routes/analytics.py`, no en `auth.py`): solo llama a `decode_token` sin buscar al usuario en la base ni exigir "mismo usuario". Los endpoints de `/analytics` confían en que el llamador (un sistema externo) ya validó a qué RUCs tiene acceso, y se los pasa explícitamente por query param `rucs` — ver `docs/endpoints.md` para el detalle de esta decisión de diseño.

### Rutas sin protección de identidad explícita

Los endpoints de `sire.py` (`GET .../propuesta`, `POST .../scrape-detalles`) usan `verify_user` (exige un JWT válido de *algún* usuario) pero no `require_same_user`: la empresa objetivo la determinan por `tenant_id`/`cliente_id`/`cuenta_id` (parámetros propios), no por el `user_id` del path. En la práctica, cualquier usuario autenticado con un JWT válido puede disparar una sincronización SIRE para cualquier terna `tenant_id/cliente_id/cuenta_id` que exista en la base, siempre que la conozca.

## Cifrado de contraseñas SOL (`app/core/encryption.py`)

Las contraseñas SOL se cifran, no se hashean, porque el sistema necesita recuperarlas en texto plano para autenticar contra la API OAuth de SUNAT (`sire_service.obtener_token_api_oficial`) y, opcionalmente, para el login del scraping Playwright.

- `_get_fernet()` deriva una clave Fernet determinística: toma `SOL_USER_CRYPTO_KEY` si está definida, si no usa `JWT_SECRET_KEY` como semilla ("Priorizar la clave compartida para sol_user" — es decir, se prefiere una clave dedicada, pero se tolera reutilizar el secreto JWT si no se configuró una separada). La semilla se pasa por SHA-256 y el digest de 32 bytes se codifica en base64 urlsafe para obtener una clave Fernet válida.
- `encrypt_password(password)` / `decrypt_password(encrypted)`: wrappers directos sobre `Fernet.encrypt`/`Fernet.decrypt`.
- **Implicación de rotación de secretos**: como la clave se deriva de `SOL_USER_CRYPTO_KEY` (o, en su ausencia, de `JWT_SECRET_KEY`), rotar `JWT_SECRET_KEY` sin haber fijado `SOL_USER_CRYPTO_KEY` invalida el descifrado de todas las contraseñas SOL ya guardadas — quedarían indescifrables hasta que se restaure el valor anterior. En producción conviene fijar `SOL_USER_CRYPTO_KEY` explícitamente y nunca rotarla sin un plan de re-cifrado.
