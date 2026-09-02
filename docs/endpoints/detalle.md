# Endpoints — Detalle SUNAT (asíncrono)

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/detalle`

[iniciar_extraccion](../../app/api/v1/routes/detalle.py:24). Dispara, en segundo plano, la extracción del detalle de ítems de cada comprobante pendiente, haciendo scraping del portal SOL con Playwright — la API SIRE no expone ese detalle línea por línea. Límite: 5/minuto.

`libro` va en la ruta porque decide en qué bandeja del portal busca el scraper: «FE Recibidas» para compras y «FE Emitidas» para ventas (`TIPO_CONSULTA` en [scraping_sunat.py](../../app/services/scraping_sunat.py)). En ventas la contraparte es el receptor, que en boletas suele ser un DNI o no venir; en ese caso el criterio de RUC se deja vacío y la búsqueda va por serie, número y fecha.

Responde de inmediato con `202 Accepted` y un `job_id`:

```json
{
  "job_id": "3f9a1c...",
  "estado": "pendiente",
  "mensaje": "Extracción iniciada. Consulta su avance en /api/v1/jobs/{job_id}"
}
```

El progreso y el resultado se consultan con [GET /api/v1/jobs/{job_id}](jobs.md). Esto reemplaza un diseño anterior donde la tarea se lanzaba con `BackgroundTasks` y se perdía todo rastro de si había terminado o fallado.

**Se ejecuta una extracción a la vez por empresa**, porque el scraper abre un Chromium y entra con la sesión SOL, que es única por usuario. Pero la segunda no se rechaza: se encola. Sólo responde `409` el duplicado exacto —mismo periodo y mismo libro ya en marcha—; otro libro u otro periodo devuelven `202` y arrancan cuando el anterior termina.

Ver también [flujo de extracción de detalle](../flujo/04-extraccion-detalle.md).
