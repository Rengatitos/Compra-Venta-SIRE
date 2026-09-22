# Endpoints — Auth y Empresas

## `POST /api/v1/auth/google`

[login_google](../../app/api/v1/routes/auth.py). Recibe `{"credential": "<ID token de Google>"}`, lo verifica contra las claves públicas de Google y comprueba el correo contra `GOOGLE_ALLOWED_EMAILS`. Devuelve `TokenResponse`: `access_token`, `token_type` y `usuario` (`email`, `nombre`, `foto`) para que el panel pinte la sesión sin decodificar el JWT.

`401` si el token de Google no es válido, `403` si la cuenta no está autorizada, `503` si Google no responde. Límite: 10/minuto. Detalles en [autenticación](../arquitectura/autenticacion.md).

## `POST /api/v1/empresas`

[crear_empresa](../../app/api/v1/routes/empresas.py). Registra una empresa nueva. **Requiere sesión.** Recibe `EmpresaCreate` (RUC de 11 dígitos, `nombre` opcional, usuario SOL, contraseña, opcionalmente `sunat_client_id`/`sunat_client_secret` propios). `409` si el RUC ya existe. Límite: 5/minuto.

## `GET /api/v1/empresas`

[listar_empresas](../../app/api/v1/routes/empresas.py). Todas las empresas registradas; es lo que alimenta el selector de cuentas del panel. Requiere sesión — ya no el header `X-Admin-Token`, que desapareció junto con el resto del acceso administrativo.

## `GET /api/v1/empresas/{ruc}`

[leer_empresa](../../app/api/v1/routes/empresas.py). Requiere sesión; `404` si no hay ninguna empresa con ese RUC. Devuelve sus datos, incluyendo el `rubro` deducido del CIIU dentro del token de SUNAT (ver [rubro.py](../../app/domain/rubro.py)).

## `PUT /api/v1/empresas/{ruc}`

[actualizar_empresa](../../app/api/v1/routes/empresas.py). Acepta cambios parciales (`EmpresaUpdate`). Si se envía `password`, se re-cifra. Un `sunat_client_id`/`sunat_client_secret` vacío en el body **no borra** el valor existente — se interpreta como "no lo toques".

## `DELETE /api/v1/empresas/{ruc}`

[eliminar_empresa](../../app/api/v1/routes/empresas.py). Borra en cascada: comprobantes, periodos, plan de cuentas, comprobantes externos (con sus fotos) y códigos de vinculación de la empresa, y finalmente la propia empresa. Los PDFs guardados en `SUNAT_DATA_DIR` no se tocan. `404` si no existe.

Cualquier sesión válida puede eliminar **cualquier** empresa: el panel no tiene roles. Con un único correo autorizado el riesgo es bajo, pero al ampliar `GOOGLE_ALLOWED_EMAILS` habrá que introducirlos.

## `POST /api/v1/empresas/{ruc}/token-sunat`

[renovar_token_sunat](../../app/api/v1/routes/empresas.py). Fuerza la obtención de un nuevo token OAuth de la API SIRE usando las credenciales de cliente de la empresa (o las globales de respaldo). Guarda el token nuevo en la empresa. `400` si no hay `sunat_client_id`/`sunat_client_secret` configurados; `502` si SUNAT rechaza la petición.

Ver también [flujo de acceso y alta de empresas](../flujo/01-registro-login.md).
