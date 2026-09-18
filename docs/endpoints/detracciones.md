# Endpoints — Detracciones (NPD)

Todos bajo `/api/v1/empresas/{ruc}/periodos/{periodo}/detracciones`. Sólo aplican a compras: la detracción la paga el adquirente. Ver el [flujo de detracciones](../flujo/07-detracciones.md).

## `GET …/detracciones/disponibilidad`

`disponibilidad` en [detracciones.py](../../app/api/v1/routes/detracciones.py). Responde `{"disponible": true}` si algún comprobante de compras del periodo trae `indDetraccion = "D"` en la propuesta del SIRE. El frontend lo usa para no ofrecer la consulta de NPD en periodos sin detracciones.

## `POST …/detracciones`

`iniciar`. Encola un job de tipo `detracciones` que entra al portal SOL, consulta los NPD (Números de Pago de Detracciones) del mes, guarda el PDF de cada uno y deja el listado en el documento del periodo. Responde `202` con un `job_id` (ver [jobs](jobs.md)). Límite: 5/minuto. Comparte cola con la extracción de detalle y la descarga de PDFs porque usa la misma sesión SOL.

La importación del ZIP oficial del RCE ([propuesta](propuesta.md)) encola este job automáticamente cuando el archivo trae filas.

## `GET …/detracciones/npds`

`listar_npds`. Devuelve `{"npds": [...], "consultado_en": ...}` tal como quedó en el periodo tras el último job: número, fecha de registro, fecha de vencimiento, importe, estado y la ruta relativa del PDF. `404` si el periodo no existe.

## `GET …/detracciones/npds/{numero}/pdf`

`descargar_pdf_npd`. Sirve el PDF de un NPD ya descargado. `422` si el número no es numérico; `404` si no está en el periodo o su PDF no existe en disco.

## `GET …/detracciones/zip`

`descargar`. ZIP con todos los PDFs de NPD del periodo (`detracciones_{periodo}.zip`). `404` si aún no hay NPD descargados.
