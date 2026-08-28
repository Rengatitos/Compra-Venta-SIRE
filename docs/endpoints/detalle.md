# Endpoints — Detalle SUNAT (asíncrono)

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/detalle`

[iniciar_extraccion](../../app/api/v1/routes/detalle.py:22). Dispara, en segundo plano, la extracción del detalle de ítems de cada comprobante pendiente, haciendo scraping del portal SOL con Playwright — la API SIRE no expone ese detalle línea por línea. Límite: 5/minuto.

Responde de inmediato con `202 Accepted` y un `job_id`:

```json
{
  "job_id": "3f9a1c...",
  "estado": "pendiente",
  "mensaje": "Extracción iniciada. Consulta su avance en /api/v1/jobs/{job_id}"
}
```

El progreso y el resultado se consultan con [GET /api/v1/jobs/{job_id}](jobs.md). Esto reemplaza un diseño anterior donde la tarea se lanzaba con `BackgroundTasks` y se perdía todo rastro de si había terminado o fallado.

Ver también [flujo de extracción de detalle](../flujo/04-extraccion-detalle.md).
