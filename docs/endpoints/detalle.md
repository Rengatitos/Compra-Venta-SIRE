# Endpoints — Detalle SUNAT (asíncrono)

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/detalle`

[iniciar_extraccion](../../app/api/v1/routes/detalle.py). Dispara, en segundo plano, la extracción del detalle de ítems de cada comprobante pendiente, haciendo scraping del portal SOL con Playwright — la API SIRE no expone ese detalle línea por línea. Límite: 5/minuto.

`libro` va en la ruta porque decide en qué bandeja del portal busca el scraper: las «Recibidas» para compras y las «Emitidas» para ventas, una por tipo de documento (`BANDEJAS` en [scraping_sunat.py](../../app/services/scraping_sunat.py)). Las series `E…` (SEE-SOL) no pasan por bandeja: se consultan en el módulo SEE-SOL correspondiente. En ventas la contraparte es el receptor: si es un RUC va en el criterio de RUC y si es un DNI u otro documento va en el criterio de documento del receptor.

Los tipos que SUNAT no publica (ver [glosa y estado](../flujo/05-glosa-y-estado.md)) no entran en el trabajo; el resultado los cuenta en `omitidos_sin_detalle`.

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
