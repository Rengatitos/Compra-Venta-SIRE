# Endpoints — PDFs de comprobantes (asíncrono)

El auditor pide el PDF de cada factura y boleta como respaldo. La API del SIRE no sirve para esto: el único endpoint suyo que devuelve un PDF es la constancia de recepción del libro, y la API de Consulta Integrada de CPE de SUNAT (`validarcomprobante`) devuelve **sólo el estado** del comprobante (`estadoCp`, `estadoRuc`, `condDomiRuc`), ni el PDF ni el XML ni el detalle. Así que el respaldo se obtiene raspando el portal SOL.

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/pdfs`

[iniciar_descarga](../../app/api/v1/routes/pdfs.py:50). Dispara en segundo plano la descarga del PDF de cada comprobante que todavía no lo tenga. Límite: 5/minuto.

Responde de inmediato con `202 Accepted` y un `job_id`; el avance se consulta en [GET /api/v1/jobs/{job_id}](jobs.md).

```json
{
  "job_id": "3f9a1c...",
  "estado": "pendiente",
  "mensaje": "Descarga de PDFs de compras iniciada. Consulta su avance en /api/v1/jobs/{job_id}"
}
```

**Comparte cola con la extracción de detalle**, porque el scraper abre un Chromium y entra con la sesión SOL, que es única por usuario: lanzar los dos a la vez haría que SUNAT invalidara una de las dos sesiones. Si hay otro trabajo del mismo RUC en marcha, este espera su turno en vez de rechazarse. Sólo responde `409` el duplicado exacto: misma empresa, mismo periodo y mismo libro ya en curso.

El trabajo corta en `SUNAT_MAX_PDFS` (100 por defecto) y lo dice en el resultado, así que un periodo grande se cubre en varias vueltas:

```json
{ "procesados": 100, "descargados": 97, "sin_pdf": 3, "pendientes": 42, "bytes": 8123456 }
```

`sin_pdf` no es un fallo del trabajo. El portal no entrega el documento de forma consistente, así que la captura intenta tres vías en orden ([`_capturar_pdf`](../../app/services/scraping_sunat.py)): pedir el PDF si el popup ya lo es, pulsar el botón de impresión si existe, y como último recurso renderizar el popup —que sólo funciona en Chromium headless—. Si ninguna funciona, ese comprobante se queda sin respaldo y se reintenta en la siguiente vuelta, porque el puntero no se guarda.

### Dónde quedan los archivos

Se escriben bajo `SUNAT_DATA_DIR` con la estructura que pidió el cliente, para que la carpeta se pueda navegar a mano:

```
{SUNAT_DATA_DIR}/{ruc}/{libro}/{año}/{mes}/{facturas|boletas|notas_credito|notas_debito}/{serie}-{numero}.pdf
data/20608997106/ventas/2026/08/boletas/B001-00001234.pdf
```

El RUC va primero aunque la estructura original no lo llevaba: la aplicación es multiempresa y sin él dos empresas con el mismo periodo se pisarían los archivos.

En Mongo sólo se guarda el puntero, en el propio documento del comprobante y con la ruta **relativa** al almacén, para que mover el volumen no invalide la base:

```json
{ "pdf_sunat": { "ruta": "20608997106/ventas/2026/08/boletas/B001-1234.pdf", "bytes": 84213, "descargado_en": "2026-09-03T13:00:00Z" } }
```

> **En Docker**: la imagen no declara ningún `VOLUME`. Sin montar un volumen en `{WORKDIR}/data` los PDFs desaparecen en cada reinicio del contenedor. `docker-compose.yml` lo monta; ver el README.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/pdfs/zip`

[exportar_zip](../../app/api/v1/routes/pdfs.py:155). Devuelve en un ZIP los PDFs ya guardados de ese periodo y libro, conservando la jerarquía de carpetas, más un **`manifiesto.csv`** que relaciona cada comprobante del registro con su archivo:

```
serie_numero;tipo_cp;fecha_emision;documento_contraparte;razon_social;total;ruta_pdf;estado
F001-1;01;2026-06-15;20129646099;ELECTROCENTRO S.A.;118.00;.../facturas/F001-1.pdf;descargado
F001-2;01;2026-06-20;20100017491;OTRO PROVEEDOR SAC;59.00;;sin_pdf
```

El manifiesto es lo que hace el ZIP auditable en vez de una bolsa de archivos, e incluye a propósito los comprobantes **sin** respaldo marcados como `sin_pdf`: un comprobante que no aparece es indistinguible de uno que no existe. Va con BOM porque lo va a abrir Excel.

`404` si todavía no se ha descargado ningún PDF de ese periodo, con un `detail` que dice que hay que correr el trabajo primero.

A diferencia del resto de las exportaciones del proyecto, que se arman en `io.BytesIO`, el ZIP se escribe en un archivo temporal y se sirve con `StreamingResponse` + limpieza en `BackgroundTask`: un periodo de ventas son cientos de boletas y el ZIP puede pasar de decenas de MB, mientras el contenedor corre con un solo worker y `MALLOC_ARENA_MAX=2`.
