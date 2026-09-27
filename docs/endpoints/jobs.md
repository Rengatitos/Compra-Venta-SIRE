# Endpoints — Jobs

Los trabajos en segundo plano los ejecuta la [cola durable](../arquitectura/cola.md): se crean en Mongo, sobreviven a reinicios y se reintentan solos ante fallos pasajeros.

## `GET /api/v1/jobs`

[listar_jobs](../../app/api/v1/routes/jobs.py). Historial de trabajos, del más reciente al más antiguo.

El RUC iba antes en el token y no se aceptaba como query param, porque el token identificaba una empresa y admitirlo del cliente habría dejado pedir el historial de otra. Ahora identifica a una persona con acceso a todas las empresas, así que va explícito: **sin `ruc` se devuelve el historial de todas**, y de un `ruc` recibido solo se comprueba que exista (`404` si no) para que un RUC mal escrito no se lea como «no hay trabajos».

| Query | Tipo | Por defecto |
|---|---|---|
| `ruc` | 11 dígitos | — (todas las empresas) |
| `periodo` | `YYYYMM` | — |
| `tipo` | `TipoJob` (tabla de abajo) | — |
| `estado` | `EstadoJob` (`pendiente`, `en_progreso`, `completado`, `fallido`) | — |
| `limit` | 1–200 | 50 |
| `skip` | ≥ 0 | 0 |

Responde `list[JobResponse]`, con la misma forma de elemento que la consulta individual de abajo.

## `GET /api/v1/jobs/{job_id}`

[obtener_job](../../app/api/v1/routes/jobs.py). Consulta el estado de cualquier trabajo asíncrono. No cuelga de `/empresas/{ruc}` y no lleva RUC: un `job_id` es único y ya no hay «otra empresa» respecto de la cual un trabajo sea ajeno. `404` si no existe.

Respuesta (`JobResponse`):

```json
{
  "job_id": "3f9a1c...",
  "tipo": "extraccion_detalles",
  "estado": "pendiente",
  "ruc": "20608997106",
  "periodo": "202606",
  "libro": "compras",
  "progreso": {"actual": 0, "total": 0, "mensaje": "En cola", "porcentaje": 0.0},
  "resultado": null,
  "error": "Timeout 25000ms exceeded",
  "creado_en": "2026-06-15T10:00:00Z",
  "actualizado_en": "2026-06-15T10:02:05Z",
  "gestionado": true,
  "solicitud_id": null,
  "intentos": 1,
  "max_intentos": 5,
  "ultimo_intento_en": "2026-06-15T10:00:01Z",
  "siguiente_intento_en": "2026-06-15T10:02:35Z",
  "historial_errores": [{"intento": 1, "en": "2026-06-15T10:02:05Z", "error": "Timeout 25000ms exceeded"}]
}
```

Un `pendiente` con `intentos > 0` está esperando un reintento: `siguiente_intento_en` dice cuándo. `gestionado: false` son registros de historial que la cola no ejecuta (la descarga SIRE síncrona) o jobs de antes de la cola.

| `tipo` | Quién lo crea | Resultado |
|---|---|---|
| `extraccion_detalles` | [detalle](detalle.md), solicitudes | `procesados`, `con_detalle`, `sin_detalle`, `descargados_pdf`, `sin_pdf`, `pendientes`, `omitidos_sin_detalle`; en una solicitud, además, `rondas` |
| `descarga_pdfs` | [pdfs](pdfs.md), por libro o el ZIP completo | `procesados`, `descargados`, `sin_pdf`, `pendientes`, `bytes`; el ZIP completo añade `zip_completo` y `nombre` |
| `detracciones` | [detracciones](detracciones.md), la descarga SIRE de compras | `npds_consultados`, `pdfs_descargados` |
| `clasificacion_cuentas` | [clasificación](clasificacion.md), solicitudes | `clasificados`, `reutilizados`, `requieren_revision`, `errores`, `errores_persistentes`, `reintentables`, `pendientes_restantes` |
| `sincronizacion_sire` | [propuesta](propuesta.md) (historial) y solicitudes | `origen` (`propuesta`, `archivo_rce`, `ticket_rce`), `nuevos`, `actualizados`, `descartados`, `sin_propuesta` |
| `alta_empresa` | [alta de empresas](empresas.md) | `estado` de la fila y `observaciones` |
| `credenciales_sunat` | solicitudes, si la empresa no las tiene | el resumen de `credenciales_sunat_service` |
| `empaquetado` | solicitudes | `archivo`, `bytes`, `carpetas` |
| `envio_correo` | solicitudes | `enviados`, `bloqueados`, `fallidos` |

## `POST /api/v1/jobs/{job_id}/reintentar`

[reintentar_job](../../app/api/v1/routes/jobs.py). Un job de la cola que quedó `fallido` vuelve a `pendiente` con los intentos a cero. `409` si no es de la cola o no está fallido; `404` si no existe.

Ver también [modelo de datos — jobs](../modelo-datos/jobs.md).
