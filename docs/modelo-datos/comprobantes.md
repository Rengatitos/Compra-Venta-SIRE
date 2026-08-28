# Modelo de datos — comprobantes

Un comprobante (factura, boleta, nota de crédito/débito, etc.), normalizado al modelo canónico de [domain/comprobante.py](../../app/domain/comprobante.py) y mapeado a BSON por [repositories/comprobantes.py](../../app/repositories/comprobantes.py).

| Campo | Tipo en Mongo | Descripción |
|---|---|---|
| `empresa_id` | str | `_id` de la empresa dueña. |
| `periodo` | str | `YYYYMM`. |
| `libro` | str | `"ventas"` \| `"compras"`. Hoy solo se escribe `"compras"`. |
| `origen` | str | `"sire"` \| `"contasis"`. Hoy solo se escribe `"sire"`. |
| `tipo_cp` | str | Código de dos caracteres del catálogo SUNAT (`"01"` factura, `"03"` boleta, etc. — ver [catalogos.py](../../app/domain/catalogos.py)). |
| `serie`, `numero` | str | Normalizados: sin ceros a la izquierda, sin separadores. Ver los normalizadores en [comprobante.py](../../app/domain/comprobante.py). |
| `serie_numero` | str | Campo derivado, `f"{serie}-{numero}"`. Es el identificador de recurso en la API (`GET .../comprobantes/{serie_numero}`). |
| `tipo_doc_identidad`, `documento_contraparte` | str | Tipo y número de documento de la contraparte, solo dígitos. |
| `razon_social` | str | Sin tildes, en mayúsculas, espacios colapsados. |
| `fecha_emision`, `fecha_vencimiento` | `datetime` (medianoche UTC) | Guardadas como fecha real, no como texto — permite agregaciones de Mongo como `$dayOfMonth`. |
| `moneda` | str | `"PEN"` por defecto. |
| `tipo_cambio` | `Decimal128` \| None | |
| `base_imponible`, `igv`, `exonerado`, `inafecto`, `isc`, `otros_tributos`, `total` | `Decimal128` | Cuantizados a 2 decimales con redondeo half-up. Ver [normalizar_monto](../../app/domain/comprobante.py). |
| `extra` | dict | Campos propios del origen que no entran al modelo común. Para `origen="sire"`, contiene `raw_sire` (el JSON crudo de la respuesta de SUNAT, como texto). |
| `estado_procesamiento` | str | `sire_recibido` → `analizado` \| `error_analisis` \| `sin_datos`. Ver [domain/comprobante.py — EstadoProcesamiento](../../app/domain/comprobante.py). Solo se establece al insertar (`$setOnInsert`); no se pisa en una resincronización. |
| `metadata_procesada` | dict \| None | Salida completa del análisis IA (ver [flujo de análisis](../flujo/05-analisis-ia.md)). |
| `detalle_sunat` | list \| None | Detalle de ítems extraído por scraping (ver [flujo de extracción de detalle](../flujo/04-extraccion-detalle.md)). Ausente hasta que se ejecuta ese job. |

## Por qué `Decimal128` y no `float`

Guardar los montos como `float` reintroduce el problema de precisión que la normalización a `Decimal` existe para evitar (ver los tests de `normalizar_monto` en [tests/domain](../../tests/domain)). Al leer, [monto_a_float](../../app/repositories/_mongo.py:32) convierte a `float` solo en el borde de la serialización JSON, donde la pérdida de precisión ya no importa.

## Índices

- `(empresa_id, periodo)` — consulta general del periodo.
- `uniq_comprobante`, único, sobre `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)` — es la clave de identidad de un comprobante. Este es el índice que reemplaza la deduplicación manual que antes corría en cada arranque: al ser una restricción de unicidad, un upsert nunca inserta el mismo comprobante dos veces.
