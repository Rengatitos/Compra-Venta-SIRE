# Endpoints — SOL Users

Prefijo `/sol-users`, montado en [main.py](../../app/main.py:111). Router en [sol_users.py](../../app/api/routes/sol_users.py).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/login` | [login](../../app/api/routes/sol_users.py:82) | Ninguna |
| POST | `/sol-users/` | [create_user](../../app/api/routes/sol_users.py:101) | Ninguna, con límite de tasa |
| GET | `/sol-users/` | [list_users](../../app/api/routes/sol_users.py:129) | verify_admin |
| GET | `/sol-users/{user_id}` | [read_user](../../app/api/routes/sol_users.py:136) | require_same_user |
| PUT | `/sol-users/{user_id}` | [update_user](../../app/api/routes/sol_users.py:142) | require_same_user |
| DELETE | `/sol-users/{user_id}` | [delete_user](../../app/api/routes/sol_users.py:167) | require_same_user |
| DELETE | `/sol-users/cleanup/{tenant_id}/{cliente_id}/{cuenta_id}` | [cleanup_sol_user](../../app/api/routes/sol_users.py:188) | verify_admin |
| POST | `/sol-users/{user_id}/refresh-token` | [refresh_sunat_token](../../app/api/routes/sol_users.py:210) | require_same_user |

Ver [autenticación](../arquitectura/autenticacion.md) para el detalle de cada dependencia de autorización, y [rate limiting](../arquitectura/rate-limiting.md) para los límites aplicados.

## Detalle de cada endpoint

**login** valida el RUC, el usuario y la contraseña (descifrando la contraseña almacenada para compararla) y devuelve un token si coinciden. Ver [flujo de registro y login](../flujo/01-registro-login.md).

**create_user** crea un usuario SOL nuevo; falla si ya existe la combinación de RUC y usuario.

**list_users** lista hasta 100 usuarios SOL. Solo accesible con el token de administrador.

**read_user** devuelve el usuario, agregando un campo de rubro de negocio inferido a partir del token de SUNAT guardado: se decodifica ese token (sin verificar su firma, solo para leer su contenido) y se mapea su código de actividad económica a un rubro mediante [_get_rubro_from_ciiu](../../app/api/routes/sol_users.py:61) y [_extract_rubro](../../app/api/routes/sol_users.py:68).

**update_user** actualiza campos parciales del usuario; si viene una nueva contraseña, la vuelve a cifrar antes de guardarla; ignora explícitamente las credenciales OAuth de SUNAT cuando llegan vacías, para no borrarlas por accidente en una actualización parcial.

**delete_user** borra el usuario y, en cascada, sus periodos y facturas asociadas.

**cleanup_sol_user** borra todos los usuarios SOL (y sus periodos y facturas) que coincidan con la combinación de tenant, cliente y cuenta recibida. Está pensado para desprovisionar por completo una cuenta del sistema externo que integra esta API.

**refresh_sunat_token** usa las credenciales OAuth guardadas del usuario para pedir un token nuevo a SUNAT y lo persiste.

## Sobre las credenciales OAuth de SUNAT

Los campos de credenciales OAuth del cliente SIRE (identificador y secreto de cliente) se ingresan manualmente al crear o actualizar un usuario, igual que cualquier otro campo. Anteriormente existía un flujo de scraping que las obtenía automáticamente navegando el portal SOL con Playwright; ese scraping de credenciales fue eliminado del código. Ver [flujo de registro y login](../flujo/01-registro-login.md) para más contexto sobre esta decisión.
