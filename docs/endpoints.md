# Endpoints HTTP

Los prefijos de path se definen en `app/main.py` al montar cada router (los routers en sí no declaran prefijo). Además de los routers, `app/main.py` define directamente:

| Método | Path | Descripción | Auth |
|---|---|---|---|
| GET | `/` | Mensaje de bienvenida (`{"mensaje": "Bienvenido a la API de Automatizacion SUNAT."}`). | Ninguna |
| GET | `/health` | Health check (`{"status": "ok"}`), usado por el `HEALTHCHECK` del `Dockerfile`. | Ninguna |

## SOL Users — prefijo `/sol-users` (`app/api/routes/sol_users.py`)

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/login` | `login` — valida RUC+usuario+password (descifrando la password almacenada) y devuelve un JWT. | Ninguna |
| POST | `/sol-users/` | `create_user` — crea un usuario SOL nuevo (falla si ya existe `ruc`+`usuario`). Rate limit 5/min. | Ninguna |
| GET | `/sol-users/` | `list_users` — lista hasta 100 usuarios SOL. | `verify_admin` (`X-Admin-Token`) |
| GET | `/sol-users/{user_id}` | `read_user` — devuelve el usuario, agregando un campo `rubro` inferido decodificando (sin verificar firma) el JWT de SUNAT guardado (`sunat_token`) y mapeando su CIIU a un rubro de negocio. | `require_same_user` |
| PUT | `/sol-users/{user_id}` | `update_user` — actualiza campos parciales; si viene `password` la vuelve a cifrar; ignora `sunat_client_id`/`sunat_client_secret` vacíos (no los borra por accidente). | `require_same_user` |
| DELETE | `/sol-users/{user_id}` | `delete_user` — borra el usuario y en cascada sus `periodos` y `facturas`. | `require_same_user` |
| DELETE | `/sol-users/cleanup/{tenant_id}/{cliente_id}/{cuenta_id}` | `cleanup_sol_user` — borra todos los usuarios SOL (y sus periodos/facturas) que coincidan con esa terna (usado para desprovisionar una cuenta completa del sistema externo). | `verify_admin` |
| POST | `/sol-users/{user_id}/refresh-token` | `refresh_sunat_token` — usa `sunat_client_id`/`sunat_client_secret` guardados para pedir un token OAuth nuevo a SUNAT y persistirlo en `sunat_token`. | `require_same_user` |

## Periods — prefijo `/sol-users/{user_id}/periodos` (`app/api/routes/periods.py`)

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/{user_id}/periodos/` | `create_period` — crea un periodo `YYYYMM` en estado `pendiente` (falla si ya existe). | `require_same_user` |
| GET | `/sol-users/{user_id}/periodos/` | `list_periods` — lista hasta 100 periodos del usuario. | `require_same_user` |
| GET | `/sol-users/{user_id}/periodos/{periodo}` | `get_period` — detalle de un periodo. | `require_same_user` |
| PUT | `/sol-users/{user_id}/periodos/{periodo}` | `update_period` — actualiza el `estado` del periodo. | `require_same_user` |
| DELETE | `/sol-users/{user_id}/periodos/{periodo}` | `delete_period` — borra el periodo y sus facturas asociadas. | `require_same_user` |

## SIRE — prefijo `/sol-users/{user_id}/periodos/{periodo}/propuesta` (`app/api/routes/sire.py`)

Nota: aunque el path incluye `{user_id}`/`{periodo}`, estos handlers en realidad reciben `tenant_id`, `cliente_id`, `cuenta_id`, `periodo` como query/path params propios y resuelven al usuario buscando esa terna en `sol_users` (no usan `user_id` del path para nada — la autorización real es solo `verify_user`, sin `require_same_user`).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/sol-users/{user_id}/periodos/{periodo}/propuesta/` | `get_sire_propuesta` — sincroniza (síncrono, bloquea el request) la propuesta de comprobantes de compra desde la API SIRE de SUNAT para `tenant_id/cliente_id/cuenta_id/periodo` y guarda/actualiza facturas. Rate limit 10/min. | `verify_user` |
| POST | `/sol-users/{user_id}/periodos/{periodo}/propuesta/scrape-detalles` | `post_scrape_detalles` — dispara en **background** (`BackgroundTasks`) el scraping Playwright del detalle de ítems de las facturas sin `detalle_compras_sunat`. Responde inmediatamente con `estado: iniciado`. Rate limit 5/min. | `verify_user` |

## Analysis — prefijo `/sol-users/{user_id}/periodos/{periodo}/analisis` (`app/api/routes/analysis.py`)

| Método | Path completo | Función | Auth |
|---|---|---|---|
| POST | `/sol-users/{user_id}/periodos/{periodo}/analisis/` | `ejecutar_analisis` — ejecuta el análisis contable con Gemini sobre las facturas pendientes del periodo. Acepta PDFs opcionales (`archivos`, multipart) como contexto RAG ad-hoc; si no se adjuntan, usa los chunks ya indexados del usuario en `vector_users`. Acepta `rubro` (default `"General"`). Rate limit 5/min. | `require_same_user` |

## Invoices — prefijo `/sol-users/{user_id}/periodos/{periodo}/facturas` (`app/api/routes/invoices.py`)

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/` | `list_invoices` — lista facturas del periodo (paginado `limit`/`skip`), deduplicadas por `_ID_REFERENCIA`. | `require_same_user` |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/export/batch` y `/facturas/batch/export` | `export_invoices_batch` — exporta todas las facturas del periodo (hasta 5000) en `format=excel|pdf`. Ambas rutas apuntan a la misma función (alias por compatibilidad con distintos clientes/versiones de frontend). | `require_same_user` |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}` | `get_invoice` — detalle de una factura por `serie_numero`. | `require_same_user` |
| PATCH | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}` | `update_invoice` — actualiza el campo `Descripcion` dentro de `metadata_procesada` (preservando si estaba guardado como string JSON o como dict). | `require_same_user` |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}/export` | `export_invoice` — exporta una factura individual en `format=pdf|excel` (default `pdf`). | `require_same_user` |

## References — prefijo `/references` (`app/api/routes/references.py`)

RAG por usuario: PDFs que el usuario sube como contexto adicional para el análisis IA.

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/references/files/{user_id}` | `listar_archivos` — nombres de documentos PDF indexados para el usuario. | `require_same_user` |
| POST | `/references/upload/{user_id}` | `subir_referencia` — sube un PDF, extrae texto (PyMuPDF), lo trocea en chunks, genera embeddings Gemini y los persiste en `vector_users`. | `require_same_user` |
| DELETE | `/references/files/{user_id}/{filename}` | `eliminar_referencia` — borra todos los chunks de ese documento para el usuario (404 si no existía ninguno). | `require_same_user` |
| GET | `/references/data/{user_id}` | `obtener_datos_vectoriales` — devuelve los chunks de texto indexados (sin el vector embedding) del usuario. | `require_same_user` |
| GET | `/references/base-topics` | `obtener_temas_base` — lista los documentos distintos presentes en la base global PCGE (`analisis_ia.vector_db`, cargada en memoria en el lifespan). | `verify_user` |

## Analytics — prefijo `/analytics` (`app/api/routes/analytics.py`)

Pensado para ser consumido por un sistema externo de "contabilidad-core" que agrega datos de varios RUCs/usuarios SOL a la vez. Usa una dependencia de auth **distinta** a las demás: `verify_dashboard_token`, que solo decodifica el JWT (`decode_token`) sin verificar que el usuario exista en la base ni exigir que sea "el mismo usuario" — el filtrado real de a qué usuarios se puede acceder ocurre vía el parámetro `rucs` (lista de RUCs separados por coma), no vía el `_id` del token. El comentario en `analytics_service.get_target_user_ids` es explícito: "el token global ya está verificado, confiamos en los RUCs que el frontend (quien llamó a contabilidad-core) nos pasa" — es decir, la autorización fina de "qué RUCs puede ver este llamador" se delega al sistema que llama, no se revalida aquí.

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/analytics/summary` | `get_summary` — totales (facturas, monto, IGV) y conteo procesadas/pendientes para los `rucs` y `periodo` dados. | `verify_dashboard_token` |
| GET | `/analytics/top-suppliers` | `get_top_suppliers` — top N proveedores por monto total (`limit`, default 5). | `verify_dashboard_token` |
| GET | `/analytics/ai-classification` | `get_ai_classification` — conteo de facturas por resultado de clasificación IA, agrupado en buckets `GASTO`/`COSTO`/`MIXTO`/`OTROS`. | `verify_dashboard_token` |
| GET | `/analytics/invoices-by-day` | `get_invoices_by_day` — cantidad de facturas por día del mes (extraído de los primeros 2 caracteres de `fecha_emision`). | `verify_dashboard_token` |
| GET | `/analytics/periodos` | `get_available_periodos` — lista de periodos con facturas para los RUCs dados, orden descendente. | `verify_dashboard_token` |
| GET | `/analytics/dashboard-data` | `get_dashboard_data` — combina en paralelo (`asyncio.gather`) summary + top proveedores + clasificación IA + facturas por día + lista de facturas (hasta 200), para poblar un dashboard en una sola llamada. | `verify_dashboard_token` |

Todos los endpoints de analytics aceptan `tipo_operacion` (default `"compras"`) para filtrar por tipo de operación registrada en cada factura.
