# Endpoints — Jobs

## `GET /api/v1/jobs/{job_id}`

[obtener_job](../../app/api/v1/routes/jobs.py:10). Consulta el estado de cualquier trabajo asíncrono. No cuelga de `/empresas/{ruc}` — la pertenencia se valida comparando `job.ruc` contra el RUC del token del solicitante. `403` si el job pertenece a otra empresa; `404` si no existe.

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

`estado` es uno de `pendiente`, `en_progreso`, `completado`, `fallido` (ver [domain/jobs.py](../../app/domain/jobs.py)). El único tipo de job que existe hoy es `extraccion_detalles` — ver [detalle](detalle.md). El contrato está diseñado para extenderse a otras operaciones asíncronas (sincronizar propuesta, aceptar/reemplazar) sin cambiar la forma de la respuesta.

Ver también [modelo de datos — jobs](../modelo-datos/jobs.md).
