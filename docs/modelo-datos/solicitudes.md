# Modelo de datos — solicitudes y cargas de empresas

## `solicitudes`

Una solicitud de procesamiento masivo. Persistida por [repositories/solicitudes.py](../../app/repositories/solicitudes.py); estados y pasos en [domain/solicitudes.py](../../app/domain/solicitudes.py).

| Campo | Tipo | Descripción |
|---|---|---|
| `creado_por` | str | Correo de quien la pidió. Recibe el ZIP completo. |
| `creado_en`, `actualizado_en`, `terminado_en` | datetime UTC | |
| `estado` | str | `en_progreso` → `empaquetando` → `enviando` → `completada` \| `completada_con_errores` \| `fallida`. |
| `clasificar` | bool | Si se pidió pasar por la IA. |
| `items` | list | Uno por empresa × periodo, ver abajo. |
| `zip` | dict \| None | `{archivo, bytes, generado_en, carpetas[]}`: lo que devolvió el empaquetado. |
| `envios` | list | Uno por destinatario: `{correo, rucs, empresas[{ruc, nombre}], periodos, estado, modo, intentos, error, definitivo, creado_en, enviado_en}`. |
| `error` | str \| None | Motivo si la solicitud acabó `fallida`. |

Cada item: `{ruc, nombre, periodo, estado, observaciones[], pasos[]}`, con `estado` en `pendiente`, `en_progreso`, `completado`, `con_errores` o `fallido`. Cada paso: `{paso, estado, job_id, nota, por_sire?}`.

- `paso` puede ser `credenciales` (solo si la empresa no tiene client_id), `sire_compras`, `sire_ventas`, `detalle_compras`, `detalle_ventas`, `clasificacion_compras` o `clasificacion_ventas`.
- `estado` puede ser `pendiente`, `encolado`, `completado`, `fallido` u `omitido`.
- `por_sire` marca los pasos que se omitieron porque falló la descarga SIRE; un reintento los reabre.

Los archivos van en `{SUNAT_DATA_DIR}/solicitudes/{id}/`: el ZIP completo (`DESCARGA_AAAA-MM-DD.zip`) y los parciales de cada cliente (`DESCARGA_AAAA-MM-DD_{huella}.zip`).

Índice: `creado_en` descendente.

## `configuracion`

Configuración editable desde el panel, un documento por área ([repositories/configuracion.py](../../app/repositories/configuracion.py)). Hoy solo `_id: "correo"`, con los campos de [ConfiguracionCorreo](../../app/domain/configuracion_correo.py):

- servidor SMTP: `host`, `puerto`, `seguridad`, `usuario` y `password_cifrada` (Fernet con `SOL_USER_CRYPTO_KEY`);
- `remitente_nombre`, `remitente_correo` y `destinatarios_permitidos`;
- `max_adjunto_mb`, `dias_enlace` y `url_publica`;
- `plantilla_asunto` y `plantilla_cuerpo`;
- quién la cambió y cuándo (`actualizado_por`, `actualizado_en`).

Sin documento, se usan los valores por defecto (sin servidor: no se envía nada).

## `cargas_empresas`

Una por alta individual o por Excel subido. Persistida por [repositories/cargas_empresas.py](../../app/repositories/cargas_empresas.py).

| Campo | Tipo | Descripción |
|---|---|---|
| `modalidad` | str | `individual` o `masiva`. |
| `archivo` | str \| None | Nombre del Excel subido. |
| `registrado_por` | str | Correo de la sesión. |
| `estado` | str | `en_progreso` mientras quede alguna fila `pendiente`; luego `completada`. |
| `progreso` | dict | `{actual, total, mensaje}`: filas terminadas. |
| `filas` | list | `{fila, ruc, razon_social, usuario, estado, motivos[], empresa_id, fecha_registro}`. **Nunca la contraseña.** |
| `creado_en`, `terminado_en` | datetime UTC | |

`estado` de la fila es `pendiente` (la empresa ya existe y la cola completa sus datos), `agregada`, `agregada_con_observaciones` o `no_agregada`. Los motivos son textos fijos (`app.domain.carga_empresas.Motivo`).

Índice: `creado_en` descendente.
