# Stage 1: Build
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# Instalar dependencias del proyecto
COPY pyproject.toml ./
COPY shared-auth-lib ./shared-auth-lib

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# Limpiar venv para reducir peso
RUN find .venv -type d -name "__pycache__" -exec rm -rf {} + && \
    find .venv -type d -name "tests" -exec rm -rf {} +

# Stage 2: Runtime
FROM python:3.12-slim-bookworm
WORKDIR /app

# Instalar dependencias del sistema necesarias para Playwright y Healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar el entorno virtual y dependencias del workspace
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/shared-auth-lib /app/shared-auth-lib

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    SUNAT_NUM_WORKERS=1

# Instalar navegadores de Playwright y sus dependencias de sistema
RUN python -m playwright install --with-deps chromium \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copiar el código de la aplicación
COPY app/ ./app/
COPY pyproject.toml ./

# Crear usuario no-root y asignar permisos
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /ms-playwright
USER appuser

# Exponer puerto
EXPOSE 9007

# Health check
HEALTHCHECK --interval=30s --timeout=15s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9007/health || exit 1

# Comando para ejecutar la aplicación con un solo worker para ahorrar RAM
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9007", "--workers", "1"]
