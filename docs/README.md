# Documentación — Sire (facturas-api)

Índice y visión general del sistema. El resto de la documentación está en esta misma carpeta:

- [`arquitectura.md`](./arquitectura.md) — estructura de carpetas, capas, patrones (auth, cifrado, rate limiting, lifespan).
- [`endpoints.md`](./endpoints.md) — todos los endpoints HTTP, agrupados por router, con método, path completo y esquema de auth.
- [`flujo-sire.md`](./flujo-sire.md) — flujo de negocio end-to-end: login → periodo → SIRE → scraping de detalle → análisis IA → export → analytics.
- [`modelo-datos.md`](./modelo-datos.md) — colecciones de MongoDB, campos principales, índices.
- [`autenticacion.md`](./autenticacion.md) — JWT, dependencias de autorización, cifrado Fernet de contraseñas SOL.

## Qué es el sistema

API en FastAPI (Python 3.12) que automatiza la gestión contable del Registro de Compras Electrónico (RCE) de SUNAT vía el sistema SIRE. Permite:

1. Registrar "usuarios SOL" (credenciales de una empresa/RUC ante SUNAT Operaciones en Línea).
2. Crear periodos fiscales (`YYYYMM`) y sincronizar la propuesta de comprobantes de compra desde la API oficial SIRE de SUNAT.
3. Opcionalmente, hacer scraping (Playwright) del detalle de ítems de cada factura directamente del portal SUNAT, porque la API SIRE no expone el detalle línea por línea.
4. Clasificar contablemente cada factura con Google Gemini usando RAG (contexto normativo PCGE global + PDFs de referencia opcionales subidos por el usuario).
5. Consultar, editar y exportar (Excel/PDF) las facturas ya procesadas.
6. Exponer analíticas agregadas (dashboard) para uno o varios RUCs a la vez, pensado para ser consumido por un sistema externo ("contabilidad-core").

El nombre del paquete en `pyproject.toml` es `facturas-api`; el repositorio se llama `Sire`.

## Stack tecnológico

- **Framework**: FastAPI (`app/main.py`), servido con Uvicorn (1 solo worker en producción, ver `Dockerfile`, para ahorrar RAM).
- **Base de datos**: MongoDB vía Motor (driver async). Una única base de datos lógica (nombre en `MONGO_FACTURASDB_NAME`, normalmente `Mod_Facturas`) contiene todas las colecciones de negocio.
- **Autenticación**: JWT propio (PyJWT), emitido en `/sol-users/login`. No hay OAuth de usuario final; el JWT identifica un "usuario SOL" (una empresa/RUC), no una persona.
- **Cifrado**: `cryptography.Fernet` para las contraseñas SOL guardadas en Mongo (no son hasheadas sino cifradas reversiblemente, porque se necesitan en texto plano para autenticar contra SUNAT).
- **Rate limiting**: `slowapi` (basado en IP remota) en endpoints sensibles (login-adyacentes, creación de usuarios, análisis IA, scraping, propuesta SIRE).
- **IA / RAG**: `google-genai` (Gemini). Embeddings con `gemini-embedding-001`, clasificación con `gemini-2.5-flash`. Búsqueda de contexto por similitud coseno en memoria (no hay vector DB dedicada; los embeddings viven en colecciones Mongo normales y se cargan a RAM).
- **Extracción de PDF**: PyMuPDF (`fitz`) para partir PDFs de referencia en chunks de texto.
- **Scraping**: Playwright (Chromium) — solo para el detalle de ítems de facturas ya sincronizadas, no para login/credenciales (ver nota abajo).
- **Exportación**: `openpyxl` (Excel) y `reportlab` (PDF).
- **Config**: `pydantic-settings` leyendo `.env` (`app/core/config.py`).

### Nota importante sobre scraping y credenciales SUNAT

Antes existía un flujo de scraping que obtenía `sunat_client_id`/`sunat_client_secret` navegando el portal SOL con Playwright. **Ese flujo fue eliminado.** Actualmente esas credenciales OAuth se ingresan manualmente como cualquier otro campo del usuario (`sunat_client_id`, `sunat_client_secret` en `SolUserCreate`/`SolUserUpdate`, ver `app/schemas/user.py`). El único uso que queda de Playwright es `app/services/scraping_sunat.py`, que solo extrae el **detalle de ítems** de facturas ya sincronizadas por la API SIRE (la API oficial no expone ese detalle línea por línea). El helper de login (`_hacer_login`) sigue documentado como "compartido" con una función `_scrape_credenciales` que ya no existe en el código — es un remanente histórico del comentario, no una función activa.

## Cómo arrancar

### Desarrollo local

```bash
cp .env.example .env
# completar variables (ver más abajo)
uv sync
uv run playwright install chromium   # solo necesario para /scrape-detalles
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

Documentación interactiva (Swagger): `http://127.0.0.1:9007/docs`.

### Docker

El `Dockerfile` usa un build multi-stage con `uv`:

1. Stage `builder`: instala dependencias de producción (`uv sync --no-install-project --no-dev`) sin devDependencies.
2. Stage runtime: imagen `python:3.12-slim-bookworm`, copia el venv ya armado, instala Chromium de Playwright (`playwright install --with-deps chromium`), corre como usuario no-root (`appuser`), expone el puerto `9007` y define un `HEALTHCHECK` contra `/health`.
3. Comando final: `uvicorn app.main:app --host 0.0.0.0 --port 9007 --workers 1`.

```bash
docker build -t sire-api .
docker run -p 9007:9007 --env-file .env sire-api
```

## Variables de entorno

Definidas en `app/core/config.py` (clase `Settings`, `pydantic-settings`, lee `.env` con `extra = "ignore"`):

| Variable | Tipo/Default | Requerida | Descripción |
|---|---|---|---|
| `PROJECT_NAME` | str, default `"Automatización SUNAT API"` | No | Título de la app FastAPI. |
| `ADMIN_TOKEN` | str | **Sí** | Token estático para endpoints admin (`X-Admin-Token`, ver `verify_admin`). |
| `JWT_SECRET_KEY` | str | **Sí** | Clave de firma HMAC del JWT. También se usa como semilla de cifrado Fernet si `SOL_USER_CRYPTO_KEY` no está definida. |
| `SOL_USER_CRYPTO_KEY` | str, opcional | No | Semilla preferida para derivar la clave Fernet de cifrado de contraseñas SOL. Si no está, se usa `JWT_SECRET_KEY`. |
| `JWT_ALGORITHM` | str, default `HS256` | No | Algoritmo de firma JWT. |
| `JWT_EXPIRE_HOURS` | int, default `2` | No | Horas de validez del JWT. |
| `MONGO_URI` | str, opcional en el schema pero requerida en la práctica | Sí | Cadena de conexión a MongoDB. |
| `MONGO_FACTURASDB_NAME` | str, opcional en el schema pero requerida en la práctica | Sí | Nombre de la base con `sol_users`, `periodos`, `facturas`, `vector_global`, `vector_users`. |
| `SUNAT_CLIENT_ID` / `SUNAT_CLIENT_SECRET` | str, opcional | No | Fallback global de credenciales OAuth SUNAT si el usuario SOL no tiene las suyas propias (ver `sire_service._obtener_credenciales_sunat`). |
| `URL_SIRE_PROPUESTA` | str | Sí (en la práctica) | Plantilla de URL de la API SIRE, con placeholder `{PERIODO}`. Debe apuntar al endpoint `.../busqueda`, no `.../comprobantes`. |
| `GEMINI_API_KEY` | leída directo con `os.getenv`, no vía `Settings` | Sí (para análisis IA) | API key de Gemini. Se usa en `app/services/analisis_ia.py`. No está declarada en `Settings`, así que no aparece documentada ahí — lo está aquí y en `.env.example`. |

`app/core/config.py` no valida en el arranque que `MONGO_URI`/`MONGO_FACTURASDB_NAME`/`URL_SIRE_PROPUESTA` estén presentes (son `Optional`), pero la app falla en tiempo de uso si faltan (conexión Mongo nula, `URL no configurada en el entorno`, etc.).
