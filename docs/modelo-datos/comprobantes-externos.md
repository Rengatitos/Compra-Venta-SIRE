# Modelo de datos — comprobantes externos y códigos de vinculación

## `comprobantes_externos`

Son los comprobantes que registra Apaclla Bot ([repositorio](../../app/repositories/comprobantes_externos.py)). Viven **aparte** de `comprobantes` a propósito, porque no vienen de SUNAT. Así:
- no les aplica `uniq_comprobante`: un Yape no tiene serie ni número;
- no los tocan la sincronización de la propuesta, el export a Excel de compras (que cuadra contra el resumen del SIRE), la auditoría ni el scraping;
- no necesitan que exista el documento del periodo.

| Campo | Tipo | Notas |
|---|---|---|
| `_id` | ObjectId | Es el `id` que se devuelve al bot |
| `empresa_id` | str | `str(empresas._id)` |
| `id_externo` | str | Id del envío en el bot (ULID); da la idempotencia |
| `libro` | `ventas` \| `compras` | |
| `fuente` | `yape` \| `plin` \| `mercado_pago` \| `niubiz` \| `boleta` \| `factura` \| `otro` | |
| `tipo_evidencia` | `voucher` \| `comprobante` | |
| `tipo_cp`, `serie`, `numero`, `nro_operacion` | str | Un voucher usa `tipo_cp "00"` y `nro_operacion` |
| `fecha_operacion` | datetime (medianoche UTC) | |
| `hora_operacion` | str \| null | |
| `moneda` | `PEN` \| `USD` | |
| `total`, `base_imponible`, `igv` | Decimal128 | |
| `contraparte` | `{tipo_doc_identidad, documento, nombre}` | |
| `descripcion`, `confianza`, `campos_dudosos` | | Lo que extrajo la visión del bot y lo que no tenía claro |
| `imagen` | `{sha256, mime, bytes, archivo}` | `archivo` es el nombre del archivo dentro de `COMPROBANTES_EXTERNOS_DIR/{empresa_id}/`; null si llegó sin foto |
| `dispositivo_id` | str | Dispositivo vinculado que lo mandó |
| `enviado_en`, `creado_en` | datetime | |
| `periodo` | str `YYYYMM` | Sale de `fecha_operacion` |
| `estado` | `recibido` | |
| `comprobante_id` | null | Reservado para conciliarlo con `comprobantes` |

Índices:
- `uniq_externo_id_externo`: único sobre `(empresa_id, id_externo)`.
- `uniq_externo_operacion`: único parcial sobre `(empresa_id, fuente, nro_operacion)`, solo cuando `nro_operacion` no está vacío.
- `uniq_externo_serie_numero`: único parcial sobre `(empresa_id, libro, tipo_cp, serie, numero)`, solo para `tipo_evidencia = "comprobante"`.
- `externos_listado`: `(empresa_id, libro, periodo, creado_en -1)`.

## `codigos_vinculacion`

Códigos de 6 dígitos para vincular un dispositivo del bot ([repositorio](../../app/repositories/codigos_vinculacion.py)). **Nunca se guarda el código en claro**, solo su sha256.

| Campo | Notas |
|---|---|
| `empresa_id`, `ruc` | |
| `codigo_hash` | sha256 del código |
| `creado_en`, `expira_en` | `expira_en = creado_en + 10 min` |
| `creado_por` | Correo de quien lo generó en el panel |
| `usado_en`, `dispositivo_id` | Se llenan al canjearlo |

Índices:
- `ttl_expira_en`: TTL sobre `expira_en`. Mongo borra solos los vencidos; los canjeados se quedan hasta entonces para poder responder `409` («ya se usó») en vez de `400`.
- `uniq_ruc_codigo`: único sobre `(ruc, codigo_hash)`.

Borrar una empresa elimina sus comprobantes externos, sus códigos y su carpeta de fotos.
