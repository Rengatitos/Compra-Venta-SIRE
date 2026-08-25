# Modelo de datos (MongoDB)

Todas las colecciones viven en una sola base lógica (`MONGO_FACTURASDB_NAME`, típicamente `Mod_Facturas`). No hay un ODM: los documentos se arman a mano como dicts en los `services`/`routes` y se validan solo parcialmente vía los schemas Pydantic de `app/schemas/`.

## `sol_users`

Una empresa/RUC con credenciales SUNAT registradas en el sistema. Poblada en `sol_users.py::create_user`.

| Campo | Tipo | Descripción |
|---|---|---|
| `_id` | ObjectId | Id de Mongo. Se usa como `user_id` en toda la API (como string). |
| `ruc` | str | RUC de la empresa. |
| `usuario` | str | Usuario SOL (SUNAT Operaciones en Línea). |
| `password` | str | Contraseña SOL **cifrada con Fernet** (no en texto plano, no hasheada — ver `docs/autenticacion.md`). |
| `sunat_token` | str/None | Token Bearer OAuth vigente de la API SIRE, cacheado para no pedir uno nuevo en cada request. Se renueva automáticamente ante un 401 o vía `POST /sol-users/{user_id}/refresh-token`. |
| `sunat_client_id` / `sunat_client_secret` | str/None | Credenciales OAuth del cliente SIRE registrado en SUNAT para esta empresa. Se ingresan manualmente (ya no se obtienen por scraping). Si están vacías, `sire_service` cae a `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET` globales. |
| `tenant_id`, `cliente_id`, `cuenta_id` | str/None | Identificadores del sistema externo que integra esta API. `sire_service.obtener_propuesta` busca al usuario por esta terna, no por `_id`. |
| `fecha_creacion` | str (ISO 8601) | Timestamp de creación. |

Índice: `ruc` (no único — puede haber múltiples usuarios con el mismo RUC pero distinto `usuario`; la unicidad real es `(ruc, usuario)`, validada solo a nivel aplicativo en `create_user`, sin índice único compuesto).

## `periodos`

Un periodo fiscal (`YYYYMM`) de sincronización SIRE para un usuario. Poblada en `periods.py::create_period`.

| Campo | Tipo | Descripción |
|---|---|---|
| `user_id` | str | `_id` del usuario SOL, como string. |
| `periodo` | str | `YYYYMM`. |
| `estado` | str | `pendiente` al crear; `terminado` cuando `sire_service.obtener_propuesta` completa la sync (con o sin comprobantes, incluyendo el caso `422`). |
| `fecha_creacion` | str (ISO, `datetime.now()` **sin** timezone — inconsistente con `sol_users.fecha_creacion` que sí usa `timezone.utc`). |

Índice: único compuesto `(user_id, periodo)`.

## `facturas`

Un comprobante de compra (factura o recibo por honorarios) sincronizado de SIRE. Poblada inicialmente por `sire_service.procesar_y_guardar_comprobantes` (upsert), enriquecida por el scraping de detalle y por el análisis IA.

| Campo | Origen | Descripción |
|---|---|---|
| `user_id`, `periodo`, `serie_numero` | SIRE (sync) | Clave lógica del documento (índice único parcial). `serie_numero` = `"{serie}-{numero}"`, ej. `F001-123`. |
| `estado_procesamiento` | SIRE → IA | `sire_recibido` (recién sincronizada) → `analizado` / `error_analisis` / `sin_datos` (tras el análisis IA). |
| `ruc_emisor`, `nombre_proveedor` | SIRE (sync, se refresca en cada sync) | Ver reglas de resolución de estos campos en `docs/flujo-sire.md` (sección 3). |
| `fecha_emision`, `fecha_anterior` | SIRE (sync) | `dd/mm/YYYY`. `fecha_anterior` es la fecha de emisión menos un día (uso no documentado explícitamente en el código consumidor visible, probablemente para filtros de rango en integraciones externas). |
| `total`, `igv` | SIRE (sync) | Montos numéricos (float). |
| `tipo_operacion` | SIRE (sync) | Siempre `"compras"` en el código actual (hay soporte de filtrado por `tipo_operacion` en analytics para una futura extensión a ventas, pero el sync solo escribe compras). |
| `raw_data` | SIRE (sync) | JSON completo del comprobante tal como lo devuelve la API SIRE, serializado a string. Es el input principal para el análisis IA. |
| `detalle_compras_sunat` | Scraping (opcional) | Lista de ítems (`cantidad`, `unidad_medida`, `codigo`, `descripcion`, `valor_unitario`, `precio_unitario`, `valor_venta`, `icbper`) extraída del portal SUNAT. Ausente si nunca se corrió el scraping para esa factura. |
| `metadata_procesada` | IA | Resultado de `analisis_ia.extraer_datos_factura`: `detalle` (líneas contables), `cuenta_contable`, `centro_costos`, `condicion_igv`, `resultado`, `ia_confidence`, `ia_status`, `Documentos`, `Descripcion`, `Observaciones`, más `_ID_REFERENCIA` (= `serie_numero`, agregado por `procesar_lote_extracciones`). Puede estar guardado como dict o como string JSON dependiendo de qué ruta lo escribió (`analysis.py` guarda dict; `invoices.py::update_invoice` preserva el tipo original al editar `Descripcion`) — por eso `invoice_service.parse_metadata` soporta ambas representaciones. |

Índices: `(user_id, periodo)`; `serie_numero` (suelto); único parcial `(user_id, periodo, serie_numero)` con `partialFilterExpression={"serie_numero": {"$gt": ""}}` (nombre `uniq_facturas_user_periodo_serie`) — la condición parcial excluye documentos con `serie_numero` vacío/ausente para no romper el índice único con datos legados que no lo tuvieran.

## `vector_global`

Base de conocimiento normativa (PCGE) compartida por todos los usuarios, cargada en memoria al arrancar (`analisis_ia.vector_db`). No se puebla desde ningún endpoint visible en este código — se asume gestionada por un proceso/script externo o carga manual directa a Mongo.

| Campo | Descripción |
|---|---|
| `texto` | Fragmento de texto normativo. |
| `metadata.documento` | Nombre del documento fuente. |
| `metadata.pagina` | Página del PDF de origen (cuando aplica). |
| `embedding` | Vector de floats (`gemini-embedding-001`). |

Índice: `metadata.documento`.

## `vector_users`

Chunks de PDFs de referencia subidos por cada usuario (`POST /references/upload/{user_id}`), usados como contexto RAG adicional específico de esa empresa.

| Campo | Descripción |
|---|---|
| `user_id` | Dueño del documento. |
| `texto`, `metadata.documento`, `metadata.pagina`, `embedding` | Igual estructura que `vector_global`. |

Índice: `(user_id, metadata.documento)`. Al re-subir un archivo con el mismo nombre para el mismo usuario, `vector_store.guardar_chunks_usuario` borra primero los chunks previos de ese documento (reemplazo completo, no merge).

## Índices creados en el lifespan (`app/main.py`)

Resumen (ver también `docs/arquitectura.md`):
- `sol_users`: `ruc`.
- `periodos`: único `(user_id, periodo)`.
- `facturas`: `(user_id, periodo)`; `serie_numero`; único parcial `(user_id, periodo, serie_numero)`.
- `vector_global`: `metadata.documento`.
- `vector_users`: `(user_id, metadata.documento)`.

La creación del índice único parcial de `facturas` está protegida con try/except: si falla (por ejemplo, por datos duplicados preexistentes que la deduplicación de arranque no llegó a limpiar), el servicio sigue arriba sin ese índice, solo con un warning en el log.
