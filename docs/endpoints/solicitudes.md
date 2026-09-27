# Endpoints — Solicitudes de procesamiento masivo

Rutas en [routes/solicitudes.py](../../app/api/v1/routes/solicitudes.py); la lógica, en [solicitudes_service.py](../../app/services/solicitudes_service.py). Todas exigen sesión salvo la descarga con enlace firmado.

## `POST /api/v1/solicitudes`

Lanza el procesamiento de empresas y periodos en segundo plano. Responde `202` con la solicitud recién creada (`SolicitudResponse`). Límite: 10/minuto.

```json
{"empresas": ["20610202251", "20603391692"], "periodos": ["202607", "202608"], "clasificar": true}
```

- `empresas`: lista de RUC o `"todas"`.
- `periodos`: lista `YYYYMM` o `"todos"` (los registrados de cada empresa). Un periodo que la empresa aún no tenga se crea; uno futuro se rechaza.
- `clasificar`: si se pasa por la IA. Con `CLASIFICADOR_HABILITADO=false` la clasificación queda «omitida» con el motivo.

`422` si la selección no se puede procesar (RUC inexistente, periodo inválido o futuro, ningún periodo, más de 500 empresas × periodos). El correo de quien la pide sale de la sesión: es el destinatario principal.

## `GET /api/v1/solicitudes`

Las 30 más recientes, sin el estado vivo de cada paso.

## `GET /api/v1/solicitudes/{id}`

La solicitud con `items` (uno por empresa × periodo) y, en cada paso, el estado vivo del job que lo ejecuta: `job_estado`, `intentos`, `max_intentos`, `siguiente_intento_en`, `mensaje` y `error`. `404` si no existe.

| `estado` de la solicitud | Significa |
|---|---|
| `en_progreso` | algún item sigue corriendo |
| `empaquetando` | todos terminaron; se generan los Excel y el ZIP |
| `enviando` | ZIP listo; se envían los correos |
| `completada` | todo bien (un destinatario bloqueado por el entorno no cuenta como error) |
| `completada_con_errores` | algún item con observaciones o algún correo fallido |
| `fallida` | todos los items sin descarga SIRE, o no se pudo generar el ZIP |

## `GET /api/v1/solicitudes/{id}/zip`

Descarga el ZIP completo. `409` si aún no está listo.

## `POST /api/v1/solicitudes/{id}/reintentar`

Vuelve a encolar lo que falló: los pasos fallidos (y los que se omitieron porque falló SIRE), o el empaquetado, o los correos fallidos. `409` si no hay nada que reintentar.

## `GET /api/v1/correos/envios`

Registro de los correos enviados: `correo`, `empresas`, `periodos`, `estado` (`pendiente`, `enviado`, `fallido`, `bloqueado`), `modo` (`adjunto` o `enlace`), `intentos`, `error`, `enviado_en`, `solicitud_id`. Hasta 100, de las solicitudes más recientes.

## `GET /api/v1/descargas/{token}`

**Sin sesión.** Es el enlace del correo cuando el ZIP no cabe como adjunto. El token es un JWT `tipo: "descarga"` con la solicitud y el archivo, y caduca a los `DESCARGA_ENLACE_DIAS`. No sirve como sesión (`usuario_actual` exige `tipo: "usuario"`), y la ruta solo sirve `.zip` de la carpeta de esa solicitud. `401` si el token no vale, `404` si el archivo ya no está. Límite: 20/minuto.

Ver [flujo de procesamiento masivo](../flujo/09-procesamiento-masivo.md) y [modelo de datos](../modelo-datos/solicitudes.md).
