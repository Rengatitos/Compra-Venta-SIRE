# Endpoints — Auth y Empresas

## `POST /api/v1/auth/google`

[login_google](../../app/api/v1/routes/auth.py). Recibe `{"credential": "<ID token de Google>"}`, lo verifica contra las claves públicas de Google y comprueba el correo contra `GOOGLE_ALLOWED_EMAILS`. Devuelve `TokenResponse`: `access_token`, `token_type` y `usuario` (`email`, `nombre`, `foto`) para que el panel pinte la sesión sin decodificar el JWT.

`401` si el token de Google no es válido, `403` si la cuenta no está autorizada, `503` si Google no responde. Límite: 10/minuto. Detalles en [autenticación](../arquitectura/autenticacion.md).

## `POST /api/v1/empresas`

[crear_empresa](../../app/api/v1/routes/empresas.py). Alta individual. **Requiere sesión.** Recibe `EmpresaCreate`: RUC con dígito verificador módulo 11, `nombre` opcional, usuario y contraseña SOL no vacíos y, opcionalmente, `sunat_client_id`/`sunat_client_secret` propios. `409` si el RUC ya existe, `422` si no es válido. Límite: 5/minuto.

Responde `201` en cuanto la empresa existe, con `carga_id` (`EmpresaCreada`). El token, el CIIU y el rubro se completan en la cola (job `alta_empresa`) y se siguen en `GET /empresas/cargas/{carga_id}`. Si no se escribieron el client_id y la clave del API SUNAT, el panel los pide aparte con `POST /empresas/{ruc}/credenciales-sunat`.

## `POST /api/v1/empresas/cargas`

[cargar_empresas](../../app/api/v1/routes/empresas.py). Carga masiva desde Excel (`.xlsx`/`.xlsm`, hasta 2 MB y 200 filas, límite 3/minuto). Se leen las columnas A a D de la primera hoja: razón social, RUC, usuario y contraseña SOL; la cabecera es opcional. Responde `202` con `{carga_id}`.

Cada fila se valida al momento: campos obligatorios, RUC con dígito verificador, duplicado dentro del archivo (vale la primera fila completa) y RUC ya registrado. Las válidas se registran en el acto, con la contraseña cifrada, y el resto del alta va a la cola. En la masiva, eso incluye las credenciales del API SUNAT si faltan. Un fallo pasajero se reintenta; si persiste, la fila queda «agregada con observaciones». La clave SOL rechazada no se reintenta.

## `GET /api/v1/empresas/cargas` · `GET /api/v1/empresas/cargas/{id}` · `GET …/{id}/reporte` · `GET /api/v1/empresas/cargas/plantilla`

Historial de cargas (sin filas), una carga con el resultado por fila, el reporte en Excel (RUC, razón social, usuario, estado, motivo, registrado por y fecha) y la plantilla vacía. Todas se declaran antes de `/{ruc}`.

## `GET /api/v1/empresas/resumen`

[resumen_empresas](../../app/api/v1/routes/empresas.py). Para el panel general. Por empresa: periodos, `ultima_actualizacion_sire` (la última descarga SIRE completada), último proceso y procesos por estado, más los totales. Los vivos se cuentan todos y los terminados, de los últimos 30 días.

## `GET /api/v1/empresas`

[listar_empresas](../../app/api/v1/routes/empresas.py). Todas las empresas registradas; es lo que alimenta el selector de cuentas del panel. Requiere sesión — ya no el header `X-Admin-Token`, que desapareció junto con el resto del acceso administrativo.

## `GET /api/v1/empresas/{ruc}`

[leer_empresa](../../app/api/v1/routes/empresas.py). Requiere sesión; `404` si no hay ninguna empresa con ese RUC. Devuelve sus datos, incluyendo el `rubro` deducido del CIIU dentro del token de SUNAT (ver [rubro.py](../../app/domain/rubro.py)).

## `PUT /api/v1/empresas/{ruc}`

[actualizar_empresa](../../app/api/v1/routes/empresas.py). Acepta cambios parciales (`EmpresaUpdate`). Si se envía `password`, se re-cifra. Un `sunat_client_id`/`sunat_client_secret` vacío en el body **no borra** el valor existente — se interpreta como "no lo toques".

`correos_notificacion` es la lista de correos a los que se envían los resultados de la empresa al terminar una [solicitud](solicitudes.md): se normaliza (minúsculas, sin duplicados), máximo 10. `null` no la toca; `[]` la vacía.

`actividades_economicas` (lista de `{tipo, ciiu, descripcion}`, la ficha RUC) es el contexto que usa el [clasificador contable](clasificacion.md). Enviarla reemplaza la lista completa. Para traerla de SUNAT en vez de escribirla: [`POST /empresas/{ruc}/ficha-ruc`](clasificacion.md).

## `DELETE /api/v1/empresas/{ruc}`

[eliminar_empresa](../../app/api/v1/routes/empresas.py). Borra en cascada: comprobantes, periodos, plan de cuentas, comprobantes externos (con sus fotos) y códigos de vinculación de la empresa, y finalmente la propia empresa. Los PDFs guardados en `SUNAT_DATA_DIR` no se tocan. `404` si no existe.

Cualquier sesión válida puede eliminar **cualquier** empresa: el panel no tiene roles. Con un único correo autorizado el riesgo es bajo, pero al ampliar `GOOGLE_ALLOWED_EMAILS` habrá que introducirlos.

## `POST /api/v1/empresas/{ruc}/token-sunat`

[renovar_token_sunat](../../app/api/v1/routes/empresas.py). Fuerza la obtención de un nuevo token OAuth de la API SIRE usando las credenciales de cliente de la empresa (o las globales de respaldo). Guarda el token nuevo en la empresa. `400` si no hay `sunat_client_id`/`sunat_client_secret` configurados; `502` si SUNAT rechaza la petición.

Ver también [flujo de acceso y alta de empresas](../flujo/01-registro-login.md).
