# Cómo arrancar

## Desarrollo local

```bash
cp .env.example .env
# completar variables (ver más abajo)
uv sync --dev
uv run playwright install chromium   # necesario para la extracción de detalle, los PDFs y las detracciones
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

O con el `Makefile`: `make back` levanta la API y `make front` el panel web (`npm run dev --prefix frontend`). Documentación interactiva (Swagger) en `http://127.0.0.1:9007/docs`.

`--reload` vigila todos los `.py` del repositorio: no editar código mientras corre un job de scraping, porque el reinicio mata el navegador (ver [ciclo de vida](arquitectura/ciclo-de-vida.md)).

## Tests y lint

```bash
uv run pytest tests -q
uv run ruff check app tests scripts
```

Los tests viven en `tests/domain/` (normalizadores, catálogos, mapeo SIRE → modelo → BSON → serialización → Excel) y `tests/services/` (glosa y estado, plantilla Excel, scraper con Playwright simulado, jobs, detracciones, reporte asociado). Ninguno requiere MongoDB ni credenciales de SUNAT: `tests/conftest.py` fija las variables de entorno mínimas y los repositorios se simulan. Ver [capas](arquitectura/capas.md).

Frontend: `npm run typecheck`, `npm run lint` y `npm test` dentro de `frontend/` (ver [frontend/README.md](../frontend/README.md)).

## Scripts

En `scripts/`, todos con `uv run python scripts/<nombre>.py --help`:

| Script | Para qué |
|---|---|
| `preparar_plantilla.py` | Regenera `app/resources/plantilla_registro.xlsx` a partir de la plantilla oficial de Contasis en `source/`, quitando las filas de notas para que los datos empiecen en la fila 4. |
| `recalcular_importes.py` | Vuelve a mapear los comprobantes guardados desde el crudo del SIRE (`extra.raw_sire`) cuando cambia el mapeo. Sin `--aplicar` sólo muestra qué haría. |
| `listar_bandejas_sol.py` | Entra al portal SOL con las credenciales de una empresa y vuelca todas las opciones del combo «Tipo de consulta» (las bandejas). Sirve para comprobar si el portal añadió alguna. |
| `informe_tipos.py` | Informe Markdown por tipo de comprobante de un RUC y periodo: cantidad, detalle, PDF, estado de glosa, ruta en SOL y la última línea del log por comprobante sin glosa. Es la evidencia de las pruebas por tipo. |

## Docker

El [Dockerfile](../Dockerfile) usa un build multi-stage con `uv`:

1. Stage `builder`: instala dependencias de producción (`uv sync --no-install-project --no-dev`), sin dependencias de desarrollo.
2. Stage runtime: imagen `python:3.12-slim-bookworm`, copia el entorno virtual ya armado, instala Chromium de Playwright (`playwright install --with-deps chromium`), corre como usuario no root (`appuser`), expone el puerto 9007 y define un healthcheck contra `/health`.
3. Comando final: Uvicorn sirviendo `app.main:app` en el puerto 9007 con un solo worker.

```bash
docker compose up --build
```

`docker-compose.yml` monta los volúmenes de `data/` (PDFs) y `logs/`; sin ellos los archivos se pierden en cada reinicio. Un solo worker en producción es una decisión deliberada para ahorrar RAM, y además la cola de jobs por empresa vive en el proceso.

## Variables de entorno

Definidas en la clase `Settings` ([config.py](../app/core/config.py), `pydantic-settings`), que lee el archivo `.env` ignorando variables adicionales no declaradas. Esta tabla es la referencia; el `README.md` raíz remite aquí.

| Variable | Tipo/Default | Requerida | Descripción |
|---|---|---|---|
| `PROJECT_NAME` | str, default "Automatización SUNAT API" | No | Título de la app FastAPI. |
| `API_V1_PREFIX` | str, default `/api/v1` | No | Prefijo bajo el que se monta el router de la API. |
| `JWT_SECRET_KEY` | str | Sí | Clave de firma HMAC del JWT. También se usa como semilla de cifrado si `SOL_USER_CRYPTO_KEY` no está definida. |
| `SOL_USER_CRYPTO_KEY` | str, opcional | No | Semilla preferida para derivar la clave de cifrado de contraseñas SOL. Ver [cifrado](arquitectura/cifrado.md). |
| `JWT_ALGORITHM` | str, default HS256 | No | Algoritmo de firma JWT. |
| `JWT_EXPIRE_HOURS` | int, default 2 | No | Horas de validez del JWT. |
| `GOOGLE_CLIENT_ID` | str | Sí (en la práctica) | Client ID del cliente OAuth de Google contra el que se valida el `aud` de los ID tokens. Sin él nadie puede entrar. Ver [autenticación](arquitectura/autenticacion.md). |
| `GOOGLE_ALLOWED_EMAILS` | lista separada por comas | Sí (en la práctica) | Correos con acceso al panel. **Una lista vacía no deja entrar a nadie**: al revés que `CORS_ORIGINS`, este campo falla cerrado a propósito. |
| `MONGO_URI` | str | Sí (en la práctica) | Cadena de conexión a MongoDB. |
| `MONGO_FACTURASDB_NAME` | str | Sí (en la práctica) | Nombre de la base con las colecciones `empresas`, `periodos`, `comprobantes`, `jobs`, `plan_cuentas`. |
| `SUNAT_CLIENT_ID` / `SUNAT_CLIENT_SECRET` | str, opcional | No | Respaldo global de credenciales OAuth SUNAT si la empresa no tiene las suyas propias. |
| `URL_SIRE_PROPUESTA` | str | Sí (en la práctica) | Plantilla de URL de la propuesta del RCE con el placeholder `{PERIODO}`. Debe apuntar al endpoint `/busqueda`. |
| `URL_SIRE_PROPUESTA_VENTAS` | str | Sí para ventas | Plantilla de URL de la propuesta del RVIE, mismo placeholder. |
| `SIRE_PER_PAGE` | int, default 100 | No | Tamaño de página al descargar la propuesta. 100 es el techo del SIRE (por encima responde 422). |
| `SIRE_MAX_PAGINAS` | int, default 50 | No | Freno por si el SIRE ignora `page`. |
| `SUNAT_SCRAPER_HEADLESS` | bool, default `true` | No | `false` abre el navegador visible, útil para diagnosticar cambios del portal. |
| `SUNAT_SCRAPER_TIMEOUT_MS` | int, default 15000 | No | Techo de espera de cada paso de Playwright. |
| `SUNAT_TIMEOUT_BUSQUEDA_MS` | int, default 25000 | No | Cuánto esperar la respuesta de una búsqueda. Sólo lo agotan los emisores lentos; los ausentes salen al instante por el aviso del portal. |
| `SUNAT_TEXTOS_SIN_RESULTADOS` | tupla, ver `config.py` | No | Avisos con los que el portal dice que no hay resultados. No va en `.env.example`: al ser compuesto, pydantic-settings lo lee como JSON. |
| `SUNAT_MAX_COMPROBANTES` | int, default 100 | No | Tope de comprobantes por extracción de detalle; el resto se informa en `pendientes`. |
| `SUNAT_DATA_DIR` | str, default `data` | No | Raíz de los PDFs descargados (relativa al repo si no es absoluta). En Docker debe ser un volumen. |
| `SUNAT_MAX_PDFS` | int, default 100 | No | Tope de PDFs por trabajo de descarga. |
| `SUNAT_PDF_TIMEOUT_MS` | int, default 20000 | No | Techo para capturar cada PDF. |
| `CORS_ORIGINS` | lista separada por comas | No | Orígenes permitidos por CORS. Default: los puertos típicos de un frontend en desarrollo local. |

La clase `Settings` no valida en el arranque que `MONGO_URI`, `MONGO_FACTURASDB_NAME` o las URL del SIRE estén presentes (son opcionales a nivel de schema), pero la aplicación falla en tiempo de uso si faltan.
