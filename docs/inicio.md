# Cómo arrancar

## Desarrollo local

```bash
cp .env.example .env
# completar variables (ver más abajo)
uv sync
uv run playwright install chromium   # solo necesario para /scrape-detalles
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

Documentación interactiva (Swagger) disponible en `http://127.0.0.1:9007/docs`.

## Docker

El [Dockerfile](../Dockerfile) usa un build multi-stage con `uv`:

1. Stage `builder`: instala dependencias de producción (`uv sync --no-install-project --no-dev`) sin dependencias de desarrollo.
2. Stage runtime: imagen `python:3.12-slim-bookworm`, copia el entorno virtual ya armado, instala Chromium de Playwright (`playwright install --with-deps chromium`), corre como usuario no root (`appuser`), expone el puerto 9007 y define un healthcheck contra `/health`.
3. Comando final: Uvicorn sirviendo `app.main:app` en el puerto 9007 con un solo worker.

```bash
docker build -t sire-api .
docker run -p 9007:9007 --env-file .env sire-api
```

Un solo worker en producción es una decisión deliberada para ahorrar RAM.

## Variables de entorno

Definidas en la clase [Settings](../app/core/config.py:5) (`pydantic-settings`), que lee el archivo `.env` ignorando variables adicionales no declaradas.

| Variable | Tipo/Default | Requerida | Descripción |
|---|---|---|---|
| PROJECT_NAME | str, default "Automatización SUNAT API" | No | Título de la app FastAPI. |
| ADMIN_TOKEN | str | Sí | Token estático para endpoints admin (header `X-Admin-Token`). Ver [autenticación](arquitectura/autenticacion.md). |
| JWT_SECRET_KEY | str | Sí | Clave de firma HMAC del JWT. También se usa como semilla de cifrado si SOL_USER_CRYPTO_KEY no está definida. |
| SOL_USER_CRYPTO_KEY | str, opcional | No | Semilla preferida para derivar la clave de cifrado de contraseñas SOL. Si no está, se usa JWT_SECRET_KEY. Ver [cifrado](arquitectura/cifrado.md). |
| JWT_ALGORITHM | str, default HS256 | No | Algoritmo de firma JWT. |
| JWT_EXPIRE_HOURS | int, default 2 | No | Horas de validez del JWT. |
| MONGO_URI | str, opcional en el schema pero requerida en la práctica | Sí | Cadena de conexión a MongoDB. |
| MONGO_FACTURASDB_NAME | str, opcional en el schema pero requerida en la práctica | Sí | Nombre de la base con las colecciones sol_users, periodos, facturas, vector_global, vector_users. |
| SUNAT_CLIENT_ID / SUNAT_CLIENT_SECRET | str, opcional | No | Fallback global de credenciales OAuth SUNAT si el usuario SOL no tiene las suyas propias. |
| URL_SIRE_PROPUESTA | str | Sí (en la práctica) | Plantilla de URL de la API SIRE, con un placeholder de periodo. Debe apuntar al endpoint de búsqueda, no al de comprobantes. |
| GEMINI_API_KEY | leída directo del entorno, no vía Settings | Sí (para análisis IA) | API key de Gemini. No está declarada en la clase Settings, así que no aparece validada ahí — solo en `.env.example`. |

La clase Settings no valida en el arranque que MONGO_URI, MONGO_FACTURASDB_NAME o URL_SIRE_PROPUESTA estén presentes (son opcionales a nivel de schema), pero la aplicación falla en tiempo de uso si faltan (conexión a Mongo nula, error de "URL no configurada en el entorno", etc.).
