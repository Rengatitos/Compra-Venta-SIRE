# Endpoints — Auth y Empresas

## `POST /api/v1/auth/login`

[login](../../app/api/v1/routes/auth.py:15). Recibe `EmpresaLogin` (RUC, usuario SOL, contraseña). Busca la empresa por RUC y compara la contraseña descifrada. Devuelve `TokenResponse` con el JWT. `401` si las credenciales no coinciden.

## `POST /api/v1/empresas`

[crear_empresa](../../app/api/v1/routes/empresas.py:29). Registra una empresa nueva. Requiere `EmpresaCreate` (RUC de 11 dígitos, usuario SOL, contraseña, opcionalmente `sunat_client_id`/`sunat_client_secret` propios). `409` si el RUC ya existe. Límite: 5/minuto. No requiere autenticación (es el endpoint de alta).

## `GET /api/v1/empresas` (admin)

[listar_empresas](../../app/api/v1/routes/empresas.py:52). Requiere el header `X-Admin-Token`. Devuelve todas las empresas registradas.

## `GET /api/v1/empresas/{ruc}`

[leer_empresa](../../app/api/v1/routes/empresas.py:60). Requiere JWT de esa misma empresa. Devuelve sus datos, incluyendo el `rubro` deducido del CIIU dentro del token de SUNAT (ver [rubro.py](../../app/domain/rubro.py)).

## `PUT /api/v1/empresas/{ruc}`

[actualizar_empresa](../../app/api/v1/routes/empresas.py:65). Acepta cambios parciales (`EmpresaUpdate`). Si se envía `password`, se re-cifra. Un `sunat_client_id`/`sunat_client_secret` vacío en el body **no borra** el valor existente — se interpreta como "no lo toques".

## `DELETE /api/v1/empresas/{ruc}`

[eliminar_empresa](../../app/api/v1/routes/empresas.py:83). Borra en cascada: comprobantes, periodos y chunks vectoriales de la empresa, y finalmente la propia empresa. `404` si no existe.

## `POST /api/v1/empresas/{ruc}/token-sunat`

[renovar_token_sunat](../../app/api/v1/routes/empresas.py:98). Fuerza la obtención de un nuevo token OAuth de la API SIRE usando las credenciales de cliente de la empresa (o las globales de respaldo). Guarda el token nuevo en la empresa. `400` si no hay `sunat_client_id`/`sunat_client_secret` configurados; `502` si SUNAT rechaza la petición.

Ver también [flujo de registro y login](../flujo/01-registro-login.md).
