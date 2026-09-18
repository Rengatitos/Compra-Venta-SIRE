# Endpoints — Jobs

## `GET /api/v1/jobs`

[listar_jobs](../../app/api/v1/routes/jobs.py). Historial de trabajos, del más reciente al más antiguo.

El RUC iba antes en el token y no se aceptaba como query param, porque el token identificaba una empresa y admitirlo del cliente habría dejado pedir el historial de otra. Ahora identifica a una persona con acceso a todas las empresas, así que va explícito: **sin `ruc` se devuelve el historial de todas**, y de un `ruc` recibido solo se comprueba que exista (`404` si no) para que un RUC mal escrito no se lea como «no hay trabajos».

| Query | Tipo | Por defecto |
|---|---|---|
| `ruc` | 11 dígitos | — (todas las empresas) |
| `periodo` | `YYYYMM` | — |
| `tipo` | `TipoJob` (`extraccion_detalles`) | — |
| `estado` | `EstadoJob` (`pendiente`, `en_progreso`, `completado`, `fallido`) | — |
| `limit` | 1–200 | 50 |
| `skip` | ≥ 0 | 0 |

Responde `list[JobResponse]`, con la misma forma de elemento que la consulta individual de abajo.

## `GET /api/v1/jobs/{job_id}`

[obtener_job](../../app/api/v1/routes/jobs.py). Consulta el estado de cualquier trabajo asíncrono. No cuelga de `/empresas/{ruc}` y no lleva RUC: un `job_id` es único y ya no hay «otra empresa» respecto de la cual un trabajo sea ajeno, así que la comprobación de pertenencia desapareció. `404` si no existe.

Respuesta (`JobResponse`):

```json
{
  "job_id": "3f9a1c...",
  "tipo": "extraccion_detalles",
  "estado": "en_progreso",
  "ruc": "20608997106",
  "periodo": "202606",
  "libro": null,
  "progreso": {"actual": 4, "total": 10, "mensaje": "Extrayendo detalle de 10 comprobantes", "porcentaje": 40.0},
  "resultado": null,
  "error": null,
  "creado_en": "2026-06-15T10:00:00Z",
  "actualizado_en": "2026-06-15T10:00:05Z"
}
```

`estado` es uno de `pendiente`, `en_progreso`, `completado`, `fallido` (ver [domain/jobs.py](../../app/domain/jobs.py)). Hay tres tipos de job (`TipoJob`):

| `tipo` | Quién lo crea | Resultado |
|---|---|---|
| `extraccion_detalles` | [detalle](detalle.md) | `procesados`, `con_detalle`, `sin_detalle`, `descargados_pdf`, `sin_pdf`, `pendientes` (recortados por el tope) y `omitidos_sin_detalle` (tipos que SUNAT no publica y no se consultan) |
| `descarga_pdfs` | [pdfs](pdfs.md), tanto la descarga por libro como el ZIP completo | `procesados`, `descargados`, `sin_pdf`, `pendientes`, `bytes`; el ZIP completo añade `zip_completo` y `nombre` |
| `detracciones` | [detracciones](detracciones.md) | `npds_consultados`, `pdfs_descargados` |

El contrato está diseñado para extenderse a otras operaciones asíncronas (sincronizar propuesta, aceptar/reemplazar) sin cambiar la forma de la respuesta.

Ver también [modelo de datos — jobs](../modelo-datos/jobs.md).
