# Inspección de código — Proyecto Sire

Fecha: 2026-08-25
Alcance: backend completo (`app/`, `shared-auth-lib/`, `pyproject.toml`, `README.md`). Todos los archivos `.py` del proyecto fueron revisados.

## 1. Resumen ejecutivo

| Categoría | Cantidad | Severidad |
|---|---|---|
| Vulnerabilidad de seguridad (endpoint sin auth) | 1 | 🔴 Crítica |
| Bugs de configuración | 2 | 🟠 Alta |
| Elementos de código muerto confirmado | 8 | 🟡 Media (limpieza segura) |
| Duplicación de lógica (DRY) | 5 focos | 🟡 Media |
| Violaciones SOLID (SRP/DIP/OCP) | ~15 focos, concentrados en 6 archivos | 🟢 Estructural (mejora de fondo) |

El código funciona, pero tiene un hueco de seguridad real, dos bugs de configuración silenciosos, un paquete Python entero duplicado sin usarse, y varios archivos ("god files") que concentran demasiadas responsabilidades — sobre todo `sol_users.py`, `analytics.py` y `analisis_ia.py`.

---

## 2. 🔴 Hallazgo crítico de seguridad

### Endpoint de borrado masivo sin autenticación

[`sol_users.py:234-253`](app/api/routes/sol_users.py#L234) — `DELETE /cleanup/{tenant_id}/{cliente_id}/{cuenta_id}`:

```python
@router.delete("/cleanup/{tenant_id}/{cliente_id}/{cuenta_id}", ...)
async def cleanup_sol_user(tenant_id: str, cliente_id: str, cuenta_id: str, db=Depends(get_user_db)):
    ...
    for user_doc in users:
        await db["periodos"].delete_many({"user_id": user_id_str})
        await db["facturas"].delete_many({"user_id": user_id_str})
        await collection.delete_one({"_id": user_doc["_id"]})
```

No tiene `Depends(verify_user)` ni `Depends(verify_admin)`. Compárese con:
- `delete_user` (línea 215) — exige `Depends(verify_user)` + chequeo de ownership.
- `list_users` (línea 171) — exige `Depends(verify_admin)`.

Cualquiera que conozca o adivine (o fuerce por fuerza bruta, ya que son strings de tenant/cliente/cuenta, no tokens) los tres IDs de path puede borrar todos los usuarios, periodos y facturas de una cuenta ajena, sin presentar ningún token. Es el endpoint más destructivo del sistema y el único sin protección.

**Recomendación:** agregar `Depends(verify_admin)` como mínimo (es una operación de limpieza cross-usuario, no algo que un usuario final SOL debería poder hacer sobre sí mismo).

### Hallazgos relacionados (menor severidad)
- [`analysis.py:22-30`](app/api/routes/analysis.py#L22) — no verifica `str(user["_id"]) != user_id` como sí hacen `periods.py`, `invoices.py` y `sol_users.py`. Un usuario autenticado puede lanzar análisis IA (con costo de Gemini) para un `user_id` que no es el suyo.
- [`analytics.py`](app/api/routes/analytics.py) — `get_target_user_ids` confía en los RUCs que envía el frontend sin verificarlos contra la identidad del token del dashboard (comentario explícito en el código: "confiamos en los RUCs que el frontend...nos pasa").

---

## 3. 🟠 Bugs de configuración

### `DB_NAME` y `DB_USER` leen la misma variable de entorno

[`app/db/database.py:7-9`](app/db/database.py#L7):

```python
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("MONGO_FACTURASDB_NAME")
DB_USER = os.getenv("MONGO_FACTURASDB_NAME")   # <- mismo nombre de variable
```

`get_db()` y `get_user_db()` —usadas en prácticamente todas las rutas vía `Depends`— terminan apuntando **al mismo database**. El README documenta una base separada `MONGO_CONTDB_NAME` ("Base maestra de contabilidad") que nunca se lee en ningún archivo del código (confirmado por grep en todo el repo). Todo indica un copy-paste bug: `DB_USER` debería leer una variable distinta (probablemente la que el README llama `MONGO_CONTDB_NAME` o una `MONGO_USERSDB_NAME` no documentada).

### `MONGO_URI` no coincide con lo documentado

Mismo archivo, línea 7: se lee `MONGO_URI` directo. Pero `.env.example` y el README solo definen `MONGO_URI_DEV` / `MONGO_URI_PROD`, seleccionadas según una variable `ENVIRONMENT` — que ningún archivo del código lee. En la práctica, la app solo conecta si alguien define manualmente una `MONGO_URI` no documentada; seguir la guía del README tal cual no funciona.

### Dos mecanismos de configuración paralelos

`app/core/config.py` centraliza settings vía `pydantic-settings` (`Settings`), pero `app/db/database.py` no lo usa — hace su propio `os.getenv()` + `load_dotenv()`. `sire_service.py` tiene el mismo problema (usa `os.getenv("SUNAT_CLIENT_ID")` en vez de `settings`). Esto significa que hay dos fuentes de verdad para configuración y es fácil que diverjan (como ya pasó arriba).

---

## 4. Código muerto confirmado

Todos verificados con grep sobre el repo completo antes de listarlos aquí.

| Elemento | Ubicación | Evidencia |
|---|---|---|
| **Paquete Python duplicado y sin usar** | `shared-auth-lib/__init__.py`, `shared-auth-lib/auth_utils.py`, `shared-auth-lib/setup.py` (nivel raíz, **no** el subpaquete) | `pyproject.toml` declara `shared-auth-lib` apuntando por path a `shared-auth-lib/pyproject.toml`, que solo empaqueta `shared_auth_lib*` (el subpaquete anidado). El `auth_utils.py` de nivel raíz es una copia vieja de `shared-auth-lib/shared_auth_lib/auth_utils.py`; nada en el repo hace `import auth_utils` a nivel top. `setup.py` es build config legado, redundante con `pyproject.toml` y con `install_requires` desincronizado (lista `motor>=3.6.0`, que no está en `pyproject.toml`). |
| **Módulo entero sin uso** | `shared-auth-lib/shared_auth_lib/activity_logs.py` | Define `get_activity_log_db`, `log_activity_event`, `list_activity_logs`, etc. Ningún símbolo del archivo se importa en ningún otro lugar del repo. Además abre su propia conexión Mongo independiente, duplicando el patrón de `app/db/database.py`. |
| **Función sin uso** | `_guardar_artifact` en [`scraping_sunat.py:24-29`](app/services/scraping_sunat.py#L24) | Nunca invocada. El campo `debug_dir` que la alimentaría nunca se setea realmente — `login_y_consultar` (línea 416) hace `result["debug_dir"] = debug_info.get("debug_dir")`, pero `debug_info` nunca contiene esa clave, así que siempre es `None`. Es una feature de debug a medio implementar. |
| **Campo sin uso** | `PROJECT_NAME` en [`config.py:6`](app/core/config.py#L6) | `main.py:138` hardcodea el título de la app (`"Automatizacion SUNAT API"`) en vez de usar `settings.PROJECT_NAME`. |
| **Dependencia sin uso** | `beautifulsoup4` en [`pyproject.toml:12`](pyproject.toml#L12) | Grep de `bs4` / `BeautifulSoup` en todo el repo: 0 resultados. El scraping se hace con Playwright. |
| **Import redundante** | `import logging` dentro de `delete_user`, [`sol_users.py:228`](app/api/routes/sol_users.py#L228) | Ya existe `logger` a nivel de módulo (línea 27); el import local es innecesario y sombrea el módulo `logging` sin razón. |
| **Ruta duplicada (a confirmar con frontend)** | `/export/batch` y `/batch/export` en `invoices.py:87-88` | Mismo handler `export_invoices_batch` registrado en dos paths distintos. No hay repo de frontend disponible para confirmar cuál está en uso real; probable alias legado que debería retirarse una vez confirmado. |
| **Variable de entorno documentada pero muerta** | `MONGO_CONTDB_NAME` | Aparece en `README.md` y `.env.example`, pero ningún archivo `.py` la lee. |

---

## 5. Duplicación de lógica (DRY)

1. **Chequeo de ownership repetido** — el patrón
   ```python
   if str(user["_id"]) != user_id:
       raise HTTPException(status_code=403, detail="...")
   ```
   aparece copiado 3-4 veces cada uno en `periods.py`, `invoices.py` y `sol_users.py` (con solo el mensaje de detalle cambiando). `references.py` ya resolvió esto con un helper `_ensure_same_user` — es el patrón a generalizar.

2. **Login SUNAT duplicado en `scraping_sunat.py`** — la secuencia de login (detección de iframe, fallback de selectores, `#btnPorRuc`, evaluación JS) está implementada completa en `_scrape_credenciales.hacer_login` (líneas 97-202) y **reimplementada de forma más pobre** (sin manejo de iframe, sin detección de mensajes de error) dentro de `_scrape_detalles` (líneas 464-503).

3. **Refresh de token duplicado dentro de la misma función** — `sire_service.obtener_propuesta` repite casi verbatim el bloque de "desencriptar password → pedir token → guardar" en el flujo inicial (líneas 167-183) y en el retry ante un 401 (líneas 199-215).

4. **Estilos ReportLab y formateo de moneda repetidos** — las 4 funciones de `export_service.py` (`generate_excel_from_invoice`, `generate_pdf_from_invoice`, `generate_excel_from_invoices_batch`, `generate_pdf_from_invoices_batch`) redefinen los mismos `ParagraphStyle` y el mismo patrón `try/except: pass` para formatear montos.

5. **Filtro Mongo repetido en `analytics.py`** — el bloque `$match`/`$or` (user_id, periodo, tipo_operacion faltante) se repite casi idéntico en las 5 funciones `_get_*_logic`.

---

## 6. Violaciones de principios SOLID

### SRP (responsabilidad única)

- **`sol_users.py` — "God file".** En un solo archivo conviven: emisión/decodificación de JWT (`_create_token`, `_decode_token`), dos dependencias de autorización distintas (`verify_user`, `verify_admin`), un clasificador de industria CIIU→rubro sin relación temática con "usuarios SOL" (líneas 68-91), CRUD completo de usuarios, y una llamada HTTP inline a la API OAuth de SUNAT con URL hardcodeada (líneas 284-317). Además, es el módulo del que **todo el resto de rutas** importa `verify_user` — convirtiéndolo de facto en el módulo de autenticación de toda la app, sin que ese sea su nombre ni su propósito declarado.
- **`analisis_ia.py`** mezcla: bootstrap del cliente Gemini (global de módulo), extracción de texto de PDF, cálculo de embeddings/similitud coseno, ingeniería de prompts (~50 líneas de string hardcodeado), y orquestación de negocio que escribe directo a `db["facturas"]`.
- **`analytics.py`** — el archivo de rutas con más lógica de negocio embebida: mezcla verificación de auth, resolución RUC→user, y 5 pipelines de agregación Mongo completos, todos dentro del archivo de rutas (contrasta con `sire.py`/`references.py`, que delegan a `app/services`). Además es el único archivo de rutas sin `response_model=` en ningún endpoint.
- **`main.py::_deduplicate_facturas`** (líneas 46-84) — una rutina completa de migración/limpieza de datos embebida en el entrypoint de la aplicación, ejecutada en cada arranque vía `lifespan`.
- **`scraping_sunat.py`** mezcla automatización de browser (Playwright), lógica de negocio de credenciales, y persistencia directa a la colección `sol_users`.
- **`invoices.py` / `periods.py`** — lógica de transformación de datos y reglas de negocio (`_serialize_factura`, `_parse_metadata`, `_dedupe_by_reference`, cascade-delete de periodos→facturas) vive directamente en las rutas, sin equivalente en `app/services`, por lo que no se puede testear ni reutilizar fuera del contexto HTTP.
- **`schemas/invoice.py::InvoiceResponse`** — modelo "gordo" que mezcla datos crudos de SUNAT, resultados del análisis de IA (`cuenta_contable`, `ia_confidence`, `ia_status`) y flags de workflow/UI (`Documentos`, `Observaciones`) en un solo contrato de datos.

### DIP (inversión de dependencias)

- Los servicios (`vector_store.py`, `analisis_ia.py`, `sire_service.py`, `scraping_sunat.py`) reciben objetos Motor/pymongo **crudos** (`db`, `col`) como parámetro, en vez de una abstracción tipo repositorio — hace imposible testearlos sin una conexión Mongo real o mockeada a mano.
- [`analisis_ia.py:15`](app/services/analisis_ia.py#L15) — `client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))` es un global construido **al importar el módulo**: si falta la env var, el import falla en seco en vez de fallar al usarse.
- `app/db/database.py` no usa el `Settings` centralizado de `app/core/config.py` — reimplementa su propia carga de env vars, causa raíz del bug de la sección 3.
- `sire_service.py` cae a `os.getenv("SUNAT_CLIENT_ID"/"SUNAT_CLIENT_SECRET")` directo en vez de pasar por `settings` (que ni siquiera declara esos campos) — inconsistente con el resto de la app.
- `analytics.py` importa el helper **privado** `_decode_token` de `sol_users.py` — un módulo de ruta acoplado directamente a un módulo de ruta hermano, en vez de depender de una abstracción de autenticación compartida.
- `app/core/encryption.py::_get_fernet()` reconstruye la clave Fernet en cada llamada, alcanzando el singleton global de `settings` dentro de la función — acoplamiento oculto, y además ineficiente (recalcula SHA-256 en cada encrypt/decrypt).

### Open/Closed y otros

- [`sol_users.py:68-82`](app/api/routes/sol_users.py#L68) — `_get_rubro_from_ciiu` es una cadena de 12 `if/elif` con prefijos de código CIIU hardcodeados; agregar un nuevo rubro requiere tocar código en vez de datos. Candidato natural a una tabla de lookup (dict o colección de config).
- Las 5 funciones `_get_*_logic` de `analytics.py` podrían unificarse con un constructor/strategy de filtros compartido en vez de reimplementar el mismo `$match` cinco veces.

### Inconsistencias transversales (no son un principio SOLID puntual, pero afectan mantenibilidad)

- **Manejo de errores inconsistente**: `analysis.py`/`sire.py` envuelven el handler en `try/except Exception` + `logger.exception` + 500; `scraping.py` hace lo mismo pero **sin loguear** la excepción; el resto deja propagar `HTTPException`s específicas sin captura genérica. Varios endpoints devuelven `str(e)` crudo al cliente (fuga menor de información interna).
- **Response models inconsistentes**: todas las rutas declaran `response_model=` salvo `analytics.py`, que devuelve dicts/listas crudas en todos sus endpoints.
- **Código síncrono bloqueando el event loop**: `sire_service.py` usa `requests` (síncrono) dentro de funciones `async def` sin `asyncio.to_thread`, a diferencia de `scraping_sunat.py`/`analisis_ia.py`, que sí lo hacen correctamente para trabajo bloqueante.

---

## 7. Patrones de diseño recomendados

- **Repository pattern** para el acceso a Mongo: envolver `db`/`col` detrás de clases repositorio inyectables (`InvoiceRepository`, `PeriodRepository`, etc.) en vez de pasar el objeto de conexión crudo a cada función de servicio. Resuelve el problema de DIP/testabilidad de la sección 6 de un solo golpe.
- **Dependency Injection unificada para auth**: una única dependencia `get_current_user` (o similar) en `app/core/auth.py` (nuevo módulo), reutilizada por todas las rutas — hoy todas dependen de `sol_users.py`, que no debería ser el dueño de la autenticación de todo el sistema. Para los dos esquemas de token que ya coexisten (SOL user vs dashboard token en `analytics.py`), un **Strategy** que elija el validador según el tipo de token entrante evitaría la lógica bifurcada actual.
- **Service/Use-case layer**: extender el patrón que ya funciona bien en `references.py` y `sire.py` (rutas delgadas que delegan a `app/services`) hacia `invoices.py`, `periods.py`, `analytics.py` y `sol_users.py`.
- **Helpers puntuales** que eliminan la duplicación de la sección 5: `_hacer_login()` único en `scraping_sunat.py`; `_refresh_token()` único en `sire_service.py`; `_fmt_money()` + constantes de estilo compartidas en `export_service.py`; una dependencia FastAPI compartida para el ownership-check (generalizando `_ensure_same_user` de `references.py`).
- **Split de schema**: dividir `InvoiceResponse` en sub-modelos compuestos por responsabilidad (datos SUNAT / resultado de IA / metadata de workflow), en vez de un único modelo con ~20 campos de tres orígenes distintos.

---

## 8. Plan de refactor por fases

Pensado para ejecutarse en tareas separadas, de menor a mayor riesgo.

### Fase A — Código muerto (bajo riesgo, alto valor) — ✅ Ejecutada 2026-08-25
- ✅ Eliminados `shared-auth-lib/__init__.py`, `shared-auth-lib/auth_utils.py`, `shared-auth-lib/setup.py` (nivel raíz).
- ✅ Eliminado `shared-auth-lib/shared_auth_lib/activity_logs.py`.
- ✅ Eliminada `_guardar_artifact` y la plumbing muerta de `debug_dir` en `scraping_sunat.py` (y el import `Path` que quedó sin uso).
- ✅ `PROJECT_NAME` ahora se usa de verdad como `title` de la app en `main.py` (en vez de eliminarlo, se conectó — es la opción de menor riesgo).
- ✅ Quitado `beautifulsoup4` de `pyproject.toml`.
- ✅ Quitado el `import logging` redundante en `sol_users.py` (`delete_user` ahora usa el `logger` de módulo).
- ⏸️ **Pendiente, requiere confirmación externa:** cuál de `/export/batch` / `/batch/export` en `invoices.py` está en uso real por el frontend — no se tocó para no romper integraciones existentes.
- ⏸️ **Pendiente, requiere decisión de negocio:** `MONGO_CONTDB_NAME` sigue documentado en README/.env.example sin leerse en código — no se tocó (ver nota en Fase B sobre `DB_NAME`/`DB_USER`).

### Fase B — Fixes críticos — ✅ Ejecutada 2026-08-25
- ✅ Agregado `Depends(verify_admin)` a `cleanup_sol_user` — ya no es un endpoint de borrado masivo sin autenticación.
- ✅ Agregado ownership check en `analysis.py` (mismo patrón que `periods.py`/`invoices.py`): ahora valida `str(user["_id"]) != user_id` antes de ejecutar el análisis.
- 🔄 **`DB_NAME`/`DB_USER` — hallazgo revisado, no era el bug que parecía.** Al releer el README con cuidado: `MONGO_FACTURASDB_NAME` está documentado explícitamente como la base que contiene `sol_users`, `periodos` **y** `facturas` juntos. Es decir, que `get_db()` y `get_user_db()` apunten a la misma base es el comportamiento documentado/intencional, no un bug de datos. `MONGO_CONTDB_NAME` (CONTABILIDAD_CORE) nunca se lee en ningún archivo de este repo — probablemente pertenece a otro microservicio (el dashboard "contabilidad-core" mencionado en `analytics.py`) que comparte el mismo `.env`, no a este backend. Como inventar una nueva variable de entorno para "separar" `DB_USER` sin confirmar esto con el equipo podía **romper el login** en producción, se optó por el cambio seguro: eliminar la llamada duplicada a `os.getenv` (`DB_USER = DB_NAME` con comentario explicando por qué), sin alterar el comportamiento. Si `MONGO_CONTDB_NAME` sí debe usarse en este servicio, es una decisión de producto/arquitectura, no una limpieza de código — recomendamos confirmarlo con quien mantiene el servicio "contabilidad-core".
- ⏸️ **Pendiente, es una decisión de producto:** si `analytics.py::get_target_user_ids` debe validar los RUCs recibidos contra la identidad del token del dashboard (hoy confía en lo que envía el frontend).

### Fase C — DRY — ✅ Ejecutada 2026-08-25
- ✅ `app/core/auth.py::require_same_user` — dependencia FastAPI compartida que reemplaza el bloque `if str(user["_id"]) != user_id: raise HTTPException(403, ...)` duplicado en `periods.py` (5x), `invoices.py` (5x), `sol_users.py` (3x) y `references.py` (su propio `_ensure_same_user`, ahora eliminado). Funciona porque FastAPI inyecta el path param `user_id` directo en la firma de la dependencia.
- ✅ `_hacer_login()` extraído como función de módulo en `scraping_sunat.py`, usado por `_scrape_credenciales` y `_scrape_detalles` (que antes reimplementaba el login sin manejo de iframe ni detección de errores).
- ✅ `_renovar_token()` extraído en `sire_service.py`, usado en la obtención inicial del token y en el retry por 401 dentro de `obtener_propuesta`.
- ✅ `analytics_service.build_match_filter()` — constructor de filtro Mongo compartido, reemplaza el `$match`/`$or` repetido 5 veces en `analytics.py`.
- ✅ `_fmt_money()` en `export_service.py` — reemplaza 3 bloques `try/except` (dos de ellos con `except:` desnudo) para formatear montos.

### Fase D — Arquitectura (SOLID de fondo) — ✅ Ejecutada 2026-08-25 (con alcance ajustado, ver nota)
- ✅ **Auth centralizada**: nuevo `app/core/auth.py` con `verify_user`, `verify_admin`, `create_token`, `decode_token`, `require_same_user`. `sol_users.py` ya no es el módulo del que depende toda la app para autenticación — ahora solo contiene CRUD de usuarios SOL. `analytics.py` ya no importa el helper privado `_decode_token` de un módulo de ruta hermano.
- ✅ **Lógica de negocio movida a services**: `invoices.py` → `app/services/invoice_service.py` (`serialize_factura`, `parse_metadata`, `dedupe_by_reference`); `analytics.py` → `app/services/analytics_service.py` (los 5 `_get_*_logic` + `get_target_user_ids`). Ambas rutas quedaron delgadas (parsing de request + delegación).
- ✅ `_deduplicate_facturas` movido de `main.py` a `app/services/maintenance.py::deduplicate_facturas`, fuera del entrypoint.
- ✅ Config unificada: `database.py` y `sire_service.py` ya no usan `os.getenv`/`load_dotenv` directo — ambos leen de `app/core/config.py::settings` (se agregaron los campos `MONGO_URI`, `MONGO_FACTURASDB_NAME`, `SUNAT_CLIENT_ID`, `SUNAT_CLIENT_SECRET`, `URL_SIRE_PROPUESTA`).
- ✅ **Extra (hallazgo relacionado, mismo archivo que se estaba tocando)**: `refresh_sunat_token` en `sol_users.py` reimplementaba inline la misma llamada OAuth que `sire_service.obtener_token_api_oficial` — ahora reutiliza esa función en vez de duplicar la petición HTTP.
- ✅ **Extra**: `sire_service.py` usaba `requests` (síncrono) dentro de funciones `async def` sin `asyncio.to_thread`, bloqueando el event loop — corregido en las 3 llamadas HTTP del archivo.
- ✅ **Extra**: `analisis_ia.py` construía el cliente Gemini a nivel de módulo (fallaba el import de toda la app si faltaba `GEMINI_API_KEY`) — ahora es un singleton perezoso (`_get_client()`), construido solo al primer uso real.
- ⏸️ **No ejecutado — alcance ajustado deliberadamente:** la introducción de una capa repository completa para todo el acceso a Mongo (recomendación de la sección 7) se dejó fuera de esta pasada. El proyecto no tiene tests automatizados; reescribir el acceso a datos de `invoices.py`, `periods.py`, `sol_users.py`, `references.py`, `sire.py`, `scraping.py` y sus servicios detrás de repositorios es un cambio de gran superficie que, sin una red de pruebas que lo respalde, es más prudente hacer de forma incremental y verificado manualmente módulo por módulo, no en un solo pase automático. Recomendado como siguiente paso si se prioriza testabilidad.

### Fase E — Schemas — ✅ Ejecutada 2026-08-25
- ✅ `InvoiceResponse` dividido en `SunatInvoiceData` (datos crudos SUNAT), `AIAnalysisData` (resultado IA) e `InvoiceWorkflowData` (metadata de workflow/UI), compuestos vía herencia múltiple en `InvoiceResponse`. El JSON de salida (nombres de campo, alias, tipos) **no cambió** — se verificó serializando un caso de prueba con `model_dump(by_alias=True)` antes y después del split.

---

## Notas de metodología

Inspección realizada con 3 agentes de exploración en paralelo (rutas API, capa de servicios, y db/schemas/shared-auth-lib) cubriendo el 100% de los archivos `.py` del proyecto, seguida de verificación manual de los hallazgos más críticos releyendo directamente `app/db/database.py`, `app/api/routes/sol_users.py` y `pyproject.toml`. Todo elemento marcado como "sin uso" o "muerto" fue confirmado con búsqueda de texto sobre el repo completo antes de incluirse en este informe.
