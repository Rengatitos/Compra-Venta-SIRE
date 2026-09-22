# Sire — API de automatización SIRE (SUNAT)

API en FastAPI y panel web en React que preparan el Registro de Compras (RCE) y el Registro de Ventas (RVIE) a partir del SIRE de SUNAT: sincronizan la propuesta de comprobantes, extraen el detalle de ítems y el PDF del portal SOL, construyen la glosa y su estado por tipo de comprobante, y exportan a la plantilla oficial de Contasis, PDF, ZIP de respaldos y reporte mensual.

El alcance vigente y los próximos pasos están en [PLAN.md](PLAN.md); la documentación técnica en [docs/](docs/README.md).

## Estructura

```
app/
  api/v1/          rutas y dependencias de la API versionada
  domain/          lógica pura: modelo canónico, normalizadores, catálogos
  repositories/    único punto de acceso a MongoDB
  services/        orquestación: SUNAT, scraping, glosa, exportación
  core/            configuración, autenticación, cifrado
  schemas/         modelos Pydantic de request/response
tests/             domain/ (modelo y catálogos) y services/ (glosa, Excel, scraper simulado, jobs); sin I/O
scripts/           utilidades de operación (plantilla, recálculo, bandejas SOL, informe por tipo)
frontend/          SPA en React + TypeScript que consume esta API (README propio)
chatbot_whatsapp/  cliente WhatsApp de esta API; captura documental, OCR local e inventario en React
```

La regla que sostiene la separación: **`domain/` no importa `app.db`, `app.repositories` ni `requests`**. Todo lo que entra son estructuras de datos, y por eso se puede testear sin Mongo ni SUNAT.

## Convención de la API

```
/api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/<recurso>
```

La identidad del recurso es el **RUC**, no el `_id` de Mongo. El sujeto sale del **JWT**, nunca del path: la dependencia `empresa_actual` contrasta el RUC del path con el del token.

| Método | Ruta (bajo `/api/v1`) | Descripción |
|---|---|---|
| `POST` | `/auth/login` | JWT a partir de RUC + usuario + clave SOL |
| `POST` `GET` | `/empresas` | Registrar empresa · listar (admin) |
| `GET` `PUT` `DELETE` | `/empresas/{ruc}` | Consultar, actualizar y eliminar |
| `POST` | `/empresas/{ruc}/token-sunat` | Renovar el token Bearer de SUNAT |
| `POST` `GET` `DELETE` | `/empresas/{ruc}/plan-cuentas` | Maestro de cuentas de la empresa (Excel de Contasis) |
| `POST` `GET` | `/empresas/{ruc}/periodos` | Ciclo de vida del periodo |
| `POST` | `…/periodos/{periodo}/libros/{libro}/propuesta` | Sincronizar la propuesta del SIRE |
| `POST` | `…/libros/compras/propuesta/archivo` | Importar el ZIP oficial de un ticket RCE |
| `GET` `PATCH` | `…/periodos/{periodo}/comprobantes` | Consultar y editar comprobantes (glosa, estado de glosa, contraparte) |
| `GET` | `…/comprobantes/{incompletos,anulados-sunat,cobertura-sunat}` | Vistas auxiliares del listado y conteo por estado de glosa |
| `GET` | `…/comprobantes/export` | Exportar a Excel (plantilla Contasis) o PDF |
| `GET` | `…/comprobantes/conciliacion-rce` | Conciliar compras con el resumen oficial del RCE |
| `POST` | `…/libros/{libro}/detalle` | Extraer detalle y PDF del portal SOL → `202` + `job_id` |
| `POST` | `…/libros/{libro}/pdfs` | Descargar los PDFs del portal SOL → `202` + `job_id` |
| `GET` | `…/libros/{libro}/pdfs/zip` | ZIP de los PDFs + `manifiesto.csv` |
| `POST` `GET` | `…/libros/{libro}/pdfs/zip-completo[/{job_id}]` | ZIP completo de compras y ventas como job |
| `POST` `GET` | `…/periodos/{periodo}/detracciones[/npds,/zip]` | NPD de detracciones: consulta como job, listado, PDFs y ZIP |
| `GET` | `…/libros/{libro}/auditoria/reporte` | Tabla comparativa con glosas y fuentes |
| `GET` | `…/periodos/{periodo}/reporte-asociado[/estado]` | Reporte mensual con libro conjunto y PDFs |
| `GET` | `/jobs` | Historial de operaciones asíncronas de la empresa |
| `GET` | `/jobs/{job_id}` | Estado y progreso de una operación asíncrona |
| `GET` | `/analytics/*` | Agregados para el dashboard externo |

Documentación interactiva en `http://127.0.0.1:9007/docs`.

## Limitaciones conocidas

- **Solo lectura contra el SIRE.** Aceptar y reemplazar propuesta requieren el flujo de escritura por ticket de SUNAT, todavía sin construir. El ticket sólo se usa para descargar el ZIP oficial del RCE.
- **Contasis solo como salida.** Se genera su plantilla oficial de compras y ventas y se carga su plan de cuentas, pero no hay parser de entrada de sus registros ni motor de conciliación.
- **Glosa según lo que publica SUNAT.** Hay tipos de comprobante que el portal no detalla (recibos de servicios, boletos, pólizas…): se entregan con los datos del SIRE, sin glosa y con la observación correspondiente. Los recibos por honorarios (02) siguen en evaluación. Ver [docs/flujo/05-glosa-y-estado.md](docs/flujo/05-glosa-y-estado.md).
- **Sin campos de auditoría.** El cliente todavía no los ha especificado, así que el reporte lleva la glosa y las fuentes pero no los campos refinados.

## Variables de entorno

La referencia completa está en [docs/inicio.md](docs/inicio.md#variables-de-entorno); `.env.example` trae todas las que conviene tocar con sus valores por defecto.

## Ejecutar

```bash
cp .env.example .env
```

```bash
uv sync --dev
```

```bash
uv run playwright install chromium
```


```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

Playwright hace falta para todo lo que entra al portal SOL: extracción de detalle, PDFs y detracciones.

«Completar con GLOSA» extrae el detalle y el PDF de cada comprobante de SUNAT. La glosa se
obtiene del detalle (o de la leyenda del comprobante) y puede editarse manualmente; cada
comprobante muestra su estado: con glosa, sin glosa, en evaluación o pendiente.

## Frontend

Con la API arriba, el panel web se levanta aparte. `CORS_ORIGINS` ya incluye `http://localhost:5173`
por defecto, y en desarrollo el proxy de Vite apunta a `127.0.0.1:9007`.

```bash
npm install --prefix frontend
```

```bash
npm run dev --prefix frontend
```

Detalles de arquitectura, diseño y accesibilidad en [frontend/README.md](frontend/README.md).

## Tests y lint

```bash
uv run pytest tests -q
```

```bash
uv run ruff check app tests scripts
```

## PDFs de los comprobantes

La extracción de detalle (`POST …/libros/{libro}/detalle`, el botón «Completar con GLOSA»)
descarga el PDF de cada comprobante en la misma visita al portal SOL en la que lee sus ítems,
y entra en la lista todo comprobante al que le falte cualquiera de las dos cosas. El trabajo
de sólo PDFs de abajo sigue disponible para repasar los que se quedaron sin respaldo.
Ambos guardan el PDF bajo `SUNAT_DATA_DIR`, con la estructura que espera el auditor:

```
data/{ruc}/{libro}/{año}/{mes}/{facturas|boletas|notas_credito|notas_debito}/{serie}-{numero}.pdf
```

El RUC va primero porque la aplicación es multiempresa: sin él, dos empresas con el mismo
periodo escribirían en la misma carpeta.

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:9007/api/v1/empresas/$RUC/periodos/202606/libros/compras/pdfs
```

Devuelve `202` con un `job_id`; el avance se sigue en `GET /api/v1/jobs/{job_id}`. Comparte
cola con la extracción de detalle, porque la sesión SOL es única por usuario: lanzar los dos a
la vez encola el segundo en vez de que se peleen.

Los PDFs ya guardados se descargan en ZIP —con un `manifiesto.csv` que los relaciona con el
registro— en `GET …/libros/{libro}/pdfs/zip`.

## Docker

```bash
docker compose up --build
```

Usar compose no es opcional si se van a descargar PDFs: la imagen no declara ningún `VOLUME`,
así que sin el volumen de `docker-compose.yml` los archivos se pierden en cada reinicio del
contenedor. Para levantarla sin compose hay que montarlo a mano:

```bash
docker build -t sire-api . && docker run -p 9007:9007 --env-file .env -v sire-pdfs:/app/data sire-api
```
