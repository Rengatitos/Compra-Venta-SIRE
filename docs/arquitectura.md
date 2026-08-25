# Arquitectura

## Estructura de carpetas

```
app/
  main.py                     # Instancia FastAPI, lifespan, montaje de routers, CORS, rate limiter
  api/
    routes/
      sol_users.py            # CRUD de usuarios SOL, login, refresh-token, cleanup
      periods.py               # CRUD de periodos fiscales
      sire.py                  # Sincronización de propuesta SIRE + scraping de detalle (background)
      analysis.py               # Disparo del análisis IA sobre facturas pendientes
      invoices.py               # Consulta/edición/exportación de facturas
      references.py             # Subida/listado/borrado de PDFs de referencia (RAG por usuario)
      analytics.py               # Endpoints agregados para dashboard externo
  core/
    config.py                  # Settings (pydantic-settings) leídas de .env
    auth.py                    # JWT create/decode, verify_user, require_same_user, verify_admin
    encryption.py               # Cifrado/descifrado Fernet de contraseñas SOL
  db/
    database.py                 # Conexión Motor, accesores get_db/get_user_db/get_vector_*_col
  schemas/
    user.py, period.py, invoice.py, generic.py   # Modelos Pydantic de request/response
  services/
    sire_service.py             # Integración OAuth + API SIRE de SUNAT
    scraping_sunat.py            # Scraping Playwright del detalle de ítems
    analisis_ia.py               # RAG + clasificación contable con Gemini
    vector_store.py              # Persistencia de embeddings en Mongo (global y por usuario)
    invoice_service.py            # Serialización/deduplicación de facturas para la API
    export_service.py             # Generación de Excel/PDF
    analytics_service.py           # Agregaciones Mongo para el dashboard
    maintenance.py                 # Deduplicación de facturas al arrancar
```

Todos los `__init__.py` están vacíos; solo marcan paquetes.

## Capas

El flujo de una request sigue siempre: **routes → services → db**.

- **routes** (`app/api/routes/*.py`): definen los `APIRouter`, validan input con schemas Pydantic, resuelven dependencias de auth (`Depends(verify_user)`, `Depends(require_same_user)`, `Depends(verify_admin)`), y delegan la lógica de negocio a `services`. Los routers en sí no montan su propio `prefix`; los prefijos (incluyendo path params como `{user_id}` y `{periodo}`) se definen al incluirlos en `app/main.py` con `app.include_router(..., prefix=...)`. Esto significa que un router como `sire.py` no sabe su propio path completo — depende de cómo se montó en `main.py`.
- **services** (`app/services/*.py`): contienen la lógica de negocio (llamadas a APIs externas de SUNAT, llamadas a Gemini, generación de reportes, agregaciones). Reciben la conexión de base de datos (`db`, `user_db`, o una colección específica) como parámetro — no importan la conexión global directamente, salvo casos puntuales de import diferido (ver `analisis_ia.cargar_vector`).
- **db** (`app/db/database.py`): capa mínima de acceso a Mongo vía Motor. Expone accesores de módulo (`get_db()`, `get_user_db()`, `get_vector_global_col()`, `get_vector_users_col()`) que leen variables globales seteadas en `connect_to_mongo()` (lifespan). `get_db()` y `get_user_db()` devuelven el **mismo** objeto de base de datos (`client[DB_NAME]` con `DB_USER = DB_NAME`): son accesores separados a propósito (para dejar claro semánticamente "esta ruta necesita datos de negocio" vs "esta ruta necesita el usuario"), no dos bases de datos distintas. Todo — `sol_users`, `periodos`, `facturas`, `vector_global`, `vector_users` — vive en la misma base lógica, nombrada por `MONGO_FACTURASDB_NAME`.

## Patrones usados

### Autenticación JWT propia

No hay OAuth de usuario final. `app/core/auth.py` implementa JWT con PyJWT:
- `create_token(user_id, ruc)` firma un payload `{user_id, ruc, exp}` con `JWT_SECRET_KEY`/`JWT_ALGORITHM`, expira en `JWT_EXPIRE_HOURS`.
- `decode_token` valida firma y expiración, lanza 401 en caso de token expirado/inválido.
- `verify_user` es una dependencia FastAPI que exige un header `Authorization: Bearer <token>`, decodifica, busca el usuario en `sol_users` por `_id` y lo retorna como dict. Si el usuario fue borrado después de emitirse el token, igual da 401 ("Usuario no encontrado").
- `require_same_user(user_id, user=Depends(verify_user))` es una dependencia compuesta que además valida que el `user_id` del path coincida con el `_id` del usuario autenticado (403 si no). Existe porque el bloque `if str(user["_id"]) != user_id: raise HTTPException(403, ...)` estaba duplicado literalmente en `periods.py`, `invoices.py`, `sol_users.py` y `analysis.py` antes de extraerse aquí.
- `verify_admin` es una dependencia separada basada en un header `X-Admin-Token` comparado contra `ADMIN_TOKEN` (no es un JWT). Se usa en endpoints de administración (listar todos los usuarios, cleanup masivo por cuenta SUNAT).

Ver detalle completo en `docs/autenticacion.md`.

### Cifrado Fernet de contraseñas SOL

Las contraseñas SOL (credenciales SUNAT de la empresa) se guardan cifradas, no hasheadas, porque el sistema necesita la contraseña en texto plano para autenticar contra la API OAuth de SUNAT y (opcionalmente) para el scraping de detalle. `app/core/encryption.py` deriva una clave Fernet determinística a partir de `SOL_USER_CRYPTO_KEY` (o `JWT_SECRET_KEY` si no está definida) vía SHA-256 + base64 urlsafe. Esto significa que **si `JWT_SECRET_KEY` cambia y `SOL_USER_CRYPTO_KEY` no estaba seteada, todas las contraseñas SOL cifradas previamente quedan indescifrables** — es un acoplamiento implícito a tener en cuenta en rotaciones de secretos.

### Rate limiting con slowapi

`app/main.py` crea un `Limiter(key_func=get_remote_address)` global (`app.state.limiter`) y registra el handler de `RateLimitExceeded`. Sin embargo, cada router que necesita límites (`sol_users.py`, `sire.py`, `analysis.py`) **vuelve a instanciar su propio `Limiter(key_func=get_remote_address)` local** y usa `@limiter.limit(...)` de esa instancia local sobre sus endpoints. Límites conocidos:
- `POST /sol-users/` (crear usuario): 5/minuto.
- `GET .../propuesta` (sincronizar SIRE): 10/minuto.
- `POST .../propuesta/scrape-detalles`: 5/minuto.
- `POST .../analisis`: 5/minuto.

### Lifespan de FastAPI (`app/main.py`)

El `lifespan` async context manager hace, en orden, al arrancar:
1. `connect_to_mongo()` — abre el cliente Motor.
2. `maintenance.deduplicate_facturas(db)` — borra facturas duplicadas (mismo `user_id`+`periodo`+`serie_numero`, quedándose con la más reciente por `_id`). Esto corre en cada arranque para evitar que datos duplicados históricos disparen doble análisis IA (cada análisis cuesta una llamada a Gemini).
3. Crea índices de negocio: `sol_users.ruc`; `periodos` único por `(user_id, periodo)`; `facturas` por `(user_id, periodo)` y por `serie_numero`; y un índice único parcial `(user_id, periodo, serie_numero)` que solo aplica cuando `serie_numero` es una cadena no vacía (`partialFilterExpression`). La creación de este último índice está envuelta en un `try/except` específico para `DuplicateKeyError`/`OperationFailure`: si ya existen datos duplicados que impiden crear el índice único, el servicio sigue funcionando igual (solo se loguea un warning) en vez de tumbar el arranque completo.
4. Crea índices en `vector_global` y `vector_users` sobre `metadata.documento` (y `user_id` en el segundo).
5. `analisis_ia.cargar_vector(vector_global)` — carga **todo** el contenido de la colección `vector_global` (la base normativa PCGE) en memoria (`analisis_ia.vector_db`, una lista de dicts con `texto`/`metadata`/`embedding`). Esto se hace una sola vez al arrancar porque la búsqueda de contexto (`buscar_contexto`) se hace por similitud coseno en memoria con NumPy, no con un índice vectorial de Mongo — para un dataset grande esto es un límite de escalabilidad conocido.

Al apagar, se llama `close_mongo_connection()`.

### CORS

`CORSMiddleware` está configurado con `allow_origins=["*"]`, `allow_credentials=True` y todos los métodos/headers permitidos — abierto a cualquier origen.
