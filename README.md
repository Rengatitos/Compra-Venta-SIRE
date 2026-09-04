# Sire — API de automatización SIRE (SUNAT)

API en FastAPI que automatiza la gestión del Registro de Compras Electrónico de SUNAT a través del SIRE: sincroniza la propuesta de comprobantes, extrae el detalle de ítems del portal SOL, clasifica contablemente con IA y exporta a Excel/PDF.

El plan de desarrollo y las decisiones de arquitectura están en [PLAN.md](PLAN.md).

## Estructura

```
app/
  api/v1/          rutas y dependencias de la API versionada
  domain/          lógica pura: modelo canónico, normalizadores, catálogos
  repositories/    único punto de acceso a MongoDB
  services/        orquestación: SUNAT, IA, scraping, exportación
  core/            configuración, autenticación, cifrado
  schemas/         modelos Pydantic de request/response
tests/domain/      tests sin I/O
frontend/          SPA en React + TypeScript que consume esta API (README propio)
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
| `GET` `POST` `DELETE` | `/empresas/{ruc}/referencias` | PDFs de referencia para el RAG |
| `POST` `GET` `DELETE` | `/empresas/{ruc}/plan-cuentas` | Maestro de cuentas de la empresa (Excel de Contasis) |
| `POST` `GET` | `/empresas/{ruc}/periodos` | Ciclo de vida del periodo |
| `POST` | `…/periodos/{periodo}/libros/{libro}/propuesta` | Sincronizar la propuesta del SIRE |
| `GET` `PATCH` | `…/periodos/{periodo}/comprobantes` | Consultar y editar comprobantes |
| `GET` | `…/comprobantes/export` | Exportar a Excel o PDF |
| `POST` | `…/libros/{libro}/analisis` | Clasificar con IA |
| `POST` | `…/libros/{libro}/detalle` | Extraer detalle del portal SOL → `202` + `job_id` |
| `POST` | `…/libros/{libro}/pdfs` | Descargar los PDFs del portal SOL → `202` + `job_id` |
| `GET` | `…/libros/{libro}/pdfs/zip` | ZIP de los PDFs + `manifiesto.csv` |
| `GET` | `…/libros/{libro}/auditoria/reporte` | Tabla comparativa con glosas y fuentes |
| `GET` | `/jobs` | Historial de operaciones asíncronas de la empresa |
| `GET` | `/jobs/{job_id}` | Estado y progreso de una operación asíncrona |
| `GET` | `/analytics/*` | Agregados para el dashboard externo |

Documentación interactiva en `http://127.0.0.1:9007/docs`.

## Limitaciones conocidas

- **Solo lectura contra el SIRE.** Aceptar y reemplazar propuesta requieren el flujo por ticket de SUNAT, todavía sin construir.
- **Sin flujo por ticket.** La descarga de las dos propuestas es JSON paginado y directo. `exportapropuesta` (que devuelve un `numTicket`) no se usa, y aceptar o reemplazar la propuesta sí lo necesitarán.
- **Contasis solo como salida.** Se genera su plantilla oficial de compras y ventas, pero no hay parser de entrada de sus Excel ni motor de conciliación, que es la pieza central del producto.
- **Sin campos de auditoría.** El cliente todavía no los ha especificado, así que el reporte lleva la glosa y las fuentes pero no los campos refinados.

## Variables de entorno

| Variable | Descripción | Requerida |
|---|---|---|
| `ADMIN_TOKEN` | Token para endpoints administrativos (header `X-Admin-Token`) | Sí |
| `JWT_SECRET_KEY` | Clave de firma del JWT | Sí |
| `JWT_ALGORITHM` | Algoritmo de firma (default `HS256`) | No |
| `JWT_EXPIRE_HOURS` | Validez del token en horas (default `2`) | No |
| `SOL_USER_CRYPTO_KEY` | Semilla para cifrar las claves SOL. Sin ella se usa `JWT_SECRET_KEY` | No |
| `MONGO_URI` | Conexión a MongoDB | Sí |
| `MONGO_FACTURASDB_NAME` | Nombre de la base | Sí |
| `SUNAT_CLIENT_ID` / `SUNAT_CLIENT_SECRET` | Credenciales del cliente API SIRE, como respaldo global | No |
| `URL_SIRE_PROPUESTA` | Plantilla de URL del RCE (compras) con el placeholder `{PERIODO}` | Sí |
| `URL_SIRE_PROPUESTA_VENTAS` | Plantilla de URL del RVIE (ventas), mismo placeholder | Sí (para ventas) |
| `SIRE_PER_PAGE` / `SIRE_MAX_PAGINAS` | Tamaño de página al descargar la propuesta y tope de páginas (default `100` / `50`) | No |
| `GEMINI_API_KEY` | API key de Gemini para el análisis contable | Sí (para IA) |
| `CORS_ORIGINS` | Orígenes permitidos, separados por comas | No |
| `SUNAT_DATA_DIR` | Raíz de los PDFs descargados del portal SOL (default `data`, relativo al repo) | No |
| `SUNAT_MAX_PDFS` | Tope de PDFs por trabajo de descarga (default `100`) | No |
| `SUNAT_PDF_TIMEOUT_MS` | Techo de espera al capturar cada PDF (default `20000`) | No |

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

Playwright solo hace falta para el endpoint de extracción de detalle.

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
uv run ruff check app tests
```

## PDFs de los comprobantes

El trabajo de descarga guarda el PDF de cada comprobante bajo `SUNAT_DATA_DIR`, con la
estructura que espera el auditor:

```
data/{ruc}/{libro}/{año}/{mes}/{facturas|boletas|notas_credito|notas_debito}/{serie}-{numero}.pdf
```

El RUC va primero porque la aplicación es multiempresa: sin él, dos empresas con el mismo
periodo escribirían en la misma carpeta.

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \n  http://127.0.0.1:9007/api/v1/empresas/$RUC/periodos/202606/libros/compras/pdfs
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
