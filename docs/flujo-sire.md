# Flujo de negocio end-to-end

## 1. Registro y login

- Se crea un usuario SOL con `POST /sol-users/` (`app/api/routes/sol_users.py::create_user`): RUC, usuario SOL, contraseña SOL (se cifra con Fernet antes de guardar, ver `docs/autenticacion.md`), y opcionalmente `sunat_client_id`/`sunat_client_secret` (credenciales OAuth del cliente SIRE registrado en SUNAT) y `tenant_id`/`cliente_id`/`cuenta_id` (identificadores del sistema externo que integra esta API).
- **Estas credenciales OAuth (`sunat_client_id`/`sunat_client_secret`) se ingresan manualmente**, igual que cualquier otro campo del usuario. Anteriormente existía un flujo de scraping que las obtenía automáticamente navegando el portal SOL con Playwright; ese scraping de credenciales fue eliminado del código. Lo único que queda de Playwright (`app/services/scraping_sunat.py`) es la extracción del detalle de ítems de facturas ya sincronizadas (paso 3).
- Login: `POST /sol-users/login` (`SolUserLogin`: ruc + usuario + password) descifra la contraseña almacenada y la compara en texto plano contra la enviada. Si coincide, `create_token` emite un JWT (`app/core/auth.py`) con `user_id` y `ruc`, válido por `JWT_EXPIRE_HOURS` horas.

## 2. Crear periodo

- `POST /sol-users/{user_id}/periodos/` (`app/api/routes/periods.py::create_period`) crea un periodo `YYYYMM` (validado con regex `^20\d{2}(0[1-9]|1[0-2])$` en `app/schemas/period.py`) en estado `pendiente`. Es único por `(user_id, periodo)` — hay un índice único de Mongo que lo garantiza además de la validación aplicativa.

## 3. Sincronizar propuesta SIRE (`app/services/sire_service.py`)

`GET /sol-users/{user_id}/periodos/{periodo}/propuesta/` → `sire_service.obtener_propuesta(tenant_id, cliente_id, cuenta_id, periodo, db, user_db)`.

1. Busca al usuario SOL por la terna `(tenant_id, cliente_id, cuenta_id)` en `sol_users` (no por `user_id` del path — ver nota en `docs/endpoints.md`).
2. Resuelve credenciales OAuth con `_obtener_credenciales_sunat`: usa `sunat_client_id`/`sunat_client_secret` del propio usuario si existen; si no, cae a las variables de entorno globales `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET` (fallback compartido, útil si todos los tenants usan el mismo cliente SIRE).
3. **Manejo de token OAuth**:
   - Si el usuario no tiene `sunat_token` guardado, se pide uno nuevo con `obtener_token_api_oficial(ruc, usuario, password, client_id, client_secret)` — un POST `grant_type=password` contra `https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/`, con `username = f"{ruc}{usuario}"` (concatenación sin separador, formato exigido por SUNAT) y `scope=https://api-sire.sunat.gob.pe`.
   - Se llama a la API SIRE (`URL_SIRE_PROPUESTA` con el placeholder `{PERIODO}` reemplazado) con `Authorization: Bearer <token>`, `codTipoOpe=1` (compras), `perPage=100`.
   - **Renovación automática ante 401**: si la API SIRE devuelve 401 (token expirado), se llama a `_renovar_token` para pedir un token nuevo y se reintenta la misma request una vez. `_renovar_token` es un helper compartido entre la obtención inicial y este retry — antes ese bloque de "desencriptar password + pedir token + guardarlo" estaba duplicado en ambos puntos del código.
   - Si no hay `client_id`/`client_secret` disponibles y el token expiró, se lanza una excepción explícita en vez de reintentar sin credenciales.
4. **Procesamiento de comprobantes** (`procesar_y_guardar_comprobantes`): por cada registro devuelto por SUNAT:
   - Solo se procesan comprobantes cuya serie empiece con `F` o `E` (facturas y recibos por honorarios/similares; se descartan boletas y otros tipos).
   - El RUC emisor se toma de `numDocIdentidadProveedor`, con fallback a `numRuc` si viene vacío o `"0"`.
   - El nombre del proveedor se resuelve probando varios campos en orden de prioridad (`desRazonSocialProveedor` → `nomRazonSocialProveedor` → `desProveedor` → `desRazonSocialEmisor` → `nomRazonSocialEmisor`), priorizando explícitamente los campos de "Proveedor" para **evitar tomar por error la razón social del comprador** (que también viene en el payload de SUNAT).
   - Se valida que la fecha de emisión (`fecEmision`) caiga dentro del `periodo` solicitado; si no, se descarta el registro (SUNAT a veces devuelve comprobantes de periodos adyacentes).
   - Se hace `update_one` con `upsert=True` sobre `facturas`, usando `$setOnInsert` para los campos "de identidad" (no se pisan si ya existía) y `$set` para los campos que sí deben refrescarse en cada sync (`ruc_emisor`, `nombre_proveedor`, montos, `raw_data`). El filtro de upsert es `(user_id, periodo, serie_numero)`.
5. Si la API SIRE responde `422`, se interpreta como "sin propuestas para ese periodo" (no es un error): se marca el periodo como `terminado` y se retorna lista vacía. Si responde `200`, igual se marca el periodo `terminado` tras guardar los comprobantes.

## 4. Scraping opcional de detalle de ítems (`app/services/scraping_sunat.py`)

`POST /sol-users/{user_id}/periodos/{periodo}/propuesta/scrape-detalles` dispara `sire_service.procesar_detalles_scraper` en background (`BackgroundTasks`, no bloquea el request HTTP — responde de inmediato con `estado: iniciado`).

- **Por qué existe**: la API SIRE solo da los totales del comprobante, no el detalle línea por línea de productos/servicios comprados. Ese detalle solo está disponible visualizando el comprobante en el portal web de SUNAT, de ahí el scraping.
- **Ya no incluye scraping de credenciales** — ver nota en la sección 1. El único uso de Playwright que queda es `obtener_detalles_facturas_recibidas`.
- Selecciona las facturas del periodo que aún no tienen `detalle_compras_sunat` (hasta 100 por corrida).
- `_scrape_detalles` (función síncrona, corre en un hilo vía `asyncio.to_thread`) usa Playwright con Chromium headless:
  1. `_hacer_login` navega a `https://e-menu.sunat.gob.pe/cl-ti-itmenu/MenuInternet.htm`, localiza el formulario de login (maneja el caso de que esté embebido en un iframe, con reintentos durante 20s), llena RUC/usuario/contraseña y detecta errores de credenciales inválidas buscando mensajes de error conocidos o texto literal en el body ("Usuario o Clave Incorrectos").
  2. Para cada factura pendiente: recarga el menú de "Consultar Factura, Boletas y Notas" (necesario para no quedarse pegado en la tabla de resultados de la búsqueda anterior), completa el formulario Dojo dentro de un iframe (`tipoConsulta=FE Recibidas`, RUC emisor, serie, número, rango de fechas = fecha de emisión), busca, y si aparece el botón "Visualizar" abre el popup del comprobante (en otro dominio, `ww1.sunat.gob.pe`) y extrae las filas de la tabla de ítems que tengan una cantidad numérica en la primera celda (filtrando encabezados/totales por una lista de palabras a excluir).
  3. Cada factura resuelta actualiza `facturas.detalle_compras_sunat` con la lista de ítems extraídos (`cantidad`, `unidad_medida`, `codigo`, `descripcion`, `valor_unitario`, `precio_unitario`, `valor_venta`, `icbper`).
- Este paso es opcional: el análisis IA (paso 5) funciona sin él, solo que sin el detalle real de ítems la clasificación se basa únicamente en los totales del `raw_data` de SUNAT.

## 5. Análisis con IA (`app/services/analisis_ia.py`, RAG con `vector_store.py`)

`POST /sol-users/{user_id}/periodos/{periodo}/analisis/` → `analisis_ia.procesar_lote_extracciones`.

- **RAG de dos niveles**:
  1. **Base global (PCGE)**: cargada una sola vez en memoria al arrancar el servidor (`analisis_ia.vector_db`, poblada por `analisis_ia.cargar_vector` en el lifespan de `app/main.py`, leyendo la colección `vector_global`). Representa normativa contable estándar (Plan Contable General Empresarial).
  2. **RAG de usuario** (por orden de prioridad, resuelto en la ruta `analysis.py`, no en el servicio): (a) PDFs adjuntados en la misma petición de análisis, procesados en memoria y **no persistidos**; si no se adjuntan, (b) los chunks previamente indexados en Mongo (`vector_users`) para ese usuario, subidos antes vía `/references/upload/{user_id}`.
- El cliente Gemini (`analisis_ia._get_client`) se construye de forma perezosa, en el primer uso, no al importar el módulo — así, si falta `GEMINI_API_KEY`, solo falla la llamada que efectivamente necesita Gemini, en vez de tumbar el import de todo el paquete de rutas al arrancar la app.
- `buscar_contexto` genera el embedding del texto de la factura (`gemini-embedding-001`) y calcula similitud coseno contra cada item de `vector_db` (global) y `vector_db_usuario`, en memoria con NumPy (no hay índice vectorial de Mongo), devolviendo el top-20 de cada fuente como texto plano de contexto.
- `extraer_datos_factura` arma un prompt con reglas de negocio explícitas (serie `F` = factura de bienes/servicios, serie `E` = honorarios/servicios profesionales), el contexto normativo, y pide a Gemini (`gemini-2.5-flash`, `response_mime_type=application/json`) un JSON con: `detalle` (líneas con producto/categoría contable/cantidad/importe/razón), `cuenta_contable`, `centro_costos`, `condicion_igv`, `resultado` (`COSTO`/`GASTO`/`ACTIVO`/`NO DETERMINADO`), `ia_confidence`, `ia_status`, `Descripcion`, `Observaciones`.
- Si la factura tiene `detalle_compras_sunat` (del scraping, paso 4), ese detalle real se concatena al texto enviado a Gemini para enriquecer la clasificación.
- Selecciona como pendientes las facturas con `estado_procesamiento` en `sire_recibido`, `error_analisis`, ausente o vacío — es decir, reintenta automáticamente las que fallaron en una corrida anterior.
- **Deduplicación defensiva por `serie_numero`** dentro del propio lote (además de la deduplicación global que corre en el lifespan, ver `docs/arquitectura.md`), para no analizar dos veces (y gastar cuota de Gemini) el mismo comprobante si hay duplicados históricos.
- Procesa todas las facturas pendientes en paralelo (`asyncio.gather`), cada una en un hilo separado (`asyncio.to_thread`) porque la librería `google-genai` usada aquí es síncrona.
- Actualiza `estado_procesamiento` a `analizado`, `error_analisis` o `sin_datos` según el resultado.

## 6. Consulta y exportación de facturas (`invoice_service.py`, `export_service.py`)

- `invoice_service.serialize_factura` combina los campos "crudos" de SIRE (`_ID_REFERENCIA`, `RUC_EMISOR`, etc.) con el resultado del análisis IA (`metadata_procesada`, que puede estar guardado como dict o como string JSON — `parse_metadata` normaliza ambos casos).
- `dedupe_by_reference` conserva solo el primer registro por `_ID_REFERENCIA` al listar/exportar, como defensa adicional ante duplicados históricos que aún no hayan sido limpiados.
- `export_service.py` genera Excel (`openpyxl`) y PDF (`reportlab`) tanto para una factura individual como para un lote completo del periodo (hasta 500 facturas en el PDF batch, límite de seguridad de tamaño/tiempo de render). Incluye una heurística de "consistencia" (`_consistency_label`) que compara la suma de `importe` del detalle IA contra el `TOTAL` real del comprobante, para marcar visualmente si el detalle generado por la IA es completo, inferido, o si amerita revisión manual.

## 7. Analytics (`analytics_service.py`)

Agregaciones Mongo (pipelines `$match`/`$group`) sobre `facturas`, filtrando por una lista de `user_ids` resuelta a partir de RUCs (`get_target_user_ids`) para soportar consultas multi-empresa desde un sistema externo. Ver `docs/endpoints.md` para el detalle de cada endpoint y la nota sobre su modelo de autorización (distinto del resto de la API: el token solo se decodifica, no se valida contra la base, y la restricción de acceso por RUC se delega al llamador).
