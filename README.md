# facturasAPI

Módulo de facturación electrónica con integración SIRE (SUNAT). Gestiona usuarios SOL, periodos fiscales y propuestas de comprobantes. Usa Google Gemini para análisis de facturas y Playwright para scraping opcional de credenciales.

## Variables de entorno

| Variable | Descripción | Requerida |
|---|---|---|
| `MONGO_URI_DEV` | Conexión a MongoDB (entorno desarrollo) | Sí |
| `MONGO_FACTURASDB_NAME` | Base con `sol_users`, `periodos` y `facturas` (`Mod_Facturas`) | Sí |
| `MONGO_CONTDB_NAME` | Base maestra de contabilidad (`CONTABILIDAD_CORE`) | Sí |
| `GEMINI_API_KEY` | API key de Google/Gemini para análisis de facturas | Sí |
| `JWT_SECRET_KEY` | Clave de firma JWT | Sí |
| `JWT_ALGORITHM` | Algoritmo de firma (`HS256`) | Sí |
| `JWT_EXPIRE_HOURS` | Validez del token en horas | No (default: 2) |
| `ADMIN_TOKEN` | Token administrativo para endpoints internos | Sí |
| `URL_SIRE_PROPUESTA` | Endpoint de la API SIRE de SUNAT | Sí |
| `GEMINI_REQUEST_MODE` | `free` (por tandas) o `normal` | No (default: `free`) |
| `GEMINI_FREE_BATCH_SIZE` | Tamaño de tanda para modo `free` | No (default: 5) |
| `GEMINI_FREE_WAIT_SECONDS` | Espera entre tandas en modo `free` (segundos) | No (default: 55) |
| `ENVIRONMENT` | `development` o `production` | No |
| `API_HOST` | Host de escucha | No (default: 0.0.0.0) |
| `API_PORT` | Puerto del servicio | No (default: 9007) |
| `MONGO_URI_PROD` | Conexión MongoDB para producción | Solo si `ENVIRONMENT=production` |

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET/POST` | `/sol-users` | Gestión de usuarios SOL |
| `GET/POST` | `/sol-users/{user_id}/periodos` | Periodos fiscales de un usuario |
| `GET` | `/sol-users/{user_id}/periodos/{periodo}/propuesta` | Propuesta SIRE del periodo |
| `POST` | `/sol-users/{user_id}/periodos/{periodo}/scraping` | Scraping de credenciales SUNAT |
| `POST` | `/sol-users/{user_id}/periodos/{periodo}/analisis` | Análisis Gemini de facturas |
| `GET/POST` | `/sol-users/{user_id}/periodos/{periodo}/facturas` | Gestión y exportación de facturas |
| `GET` | `/references` | Datos de referencia |
| `GET` | `/health` | Estado del servicio |

## Playwright

Solo requerido para el endpoint de scraping:

```bash
playwright install chromium
```

## Nota sobre SIRE

`URL_SIRE_PROPUESTA` debe usar el endpoint `/busqueda` (no `/comprobantes`):

```
https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros/rce/propuesta/web/propuesta/{PERIODO}/busqueda
```

Si Gemini responde `429 RESOURCE_EXHAUSTED`, usar `GEMINI_REQUEST_MODE=free` con `GEMINI_FREE_WAIT_SECONDS=55`.

## Ejecutar

```bash
cp .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

Documentación interactiva: `http://127.0.0.1:9007/docs`
