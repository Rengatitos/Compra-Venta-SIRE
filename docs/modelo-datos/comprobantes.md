# Modelo de datos — comprobantes

Un comprobante (factura, boleta, nota de crédito/débito, etc.), normalizado al modelo canónico de [domain/comprobante.py](../../app/domain/comprobante.py) y mapeado a BSON por [repositories/comprobantes.py](../../app/repositories/comprobantes.py).

| Campo | Tipo en Mongo | Descripción |
|---|---|---|
| `empresa_id` | str | `_id` de la empresa dueña. |
| `periodo` | str | `YYYYMM`. |
| `libro` | str | `"ventas"` \| `"compras"`. Discrimina el libro electrónico; los dos se escriben. |
| `origen` | str | `"sire"` \| `"contasis"`. Hoy solo se escribe `"sire"`. |
| `tipo_cp` | str | Código de dos caracteres del catálogo SUNAT (`"01"` factura, `"03"` boleta, etc. — ver [catalogos.py](../../app/domain/catalogos.py)). |
| `serie`, `numero` | str | Normalizados: sin ceros a la izquierda, sin separadores. Ver los normalizadores en [comprobante.py](../../app/domain/comprobante.py). |
| `serie_numero` | str | Campo derivado, `f"{serie}-{numero}"`. Es el identificador de recurso en la API (`GET .../comprobantes/{serie_numero}`). |
| `tipo_doc_identidad`, `documento_contraparte` | str | Tipo y número de documento de la contraparte, solo dígitos. |
| `razon_social` | str | Sin tildes, en mayúsculas, espacios colapsados. |
| `fecha_emision`, `fecha_vencimiento` | `datetime` (medianoche UTC) | Guardadas como fecha real, no como texto — permite agregaciones de Mongo como `$dayOfMonth`. |
| `moneda` | str | `"PEN"` por defecto. |
| `tipo_cambio` | `Decimal128` \| None | |
| `porcentaje_igv` | `Decimal128` \| None | Tasa en puntos porcentuales (18, 10.5 en selva). `None` cuando el comprobante no la trae. |
| `base_imponible`, `igv`, `exonerado`, `inafecto`, `no_gravado`, `isc`, `icbper`, `otros_tributos`, `total` | `Decimal128` | Cuantizados a 2 decimales con redondeo half-up. Ver [normalizar_monto](../../app/domain/comprobante.py). |
| `base_imponible_dg`, `igv_dg`, `base_imponible_dgng`, `igv_dgng`, `base_imponible_dng`, `igv_dng` | `Decimal128` | Desglose por destino de la adquisición. Solo el RCE lo trae; en ventas van en cero. |

`no_gravado` corresponde al "valor de las adquisiciones no gravadas" del RCE. SUNAT **no** separa exonerado de inafecto en el registro de compras: los agrupa en ese único importe, así que repartirlo entre `exonerado` e `inafecto` sería inventar una distinción que el dato no trae. En ventas el RVIE **sí** los separa, y esos dos campos se llenan.

### El desglose por destino

El RCE reparte la base imponible y el IGV según a qué destine la empresa la adquisición: gravadas (`DG`), gravadas y no gravadas a la vez (`DGNG`) y no gravadas (`DNG`). `base_imponible` e `igv` son la **suma de los tres**, y cada destino se guarda además por separado porque el registro de compras de Contasis los pide en columnas distintas: mandarlo todo a la columna de gravadas declararía como tal lo que fue a operaciones no gravadas.

En la inmensa mayoría de comprobantes todo cae en `DG` y los otros cuatro campos van en cero.

### Tasa de IGV

Se guarda `None`, no la tasa general, cuando SUNAT no la manda: el modelo de dominio no inventa un 18 % que falsearía los comprobantes no gravados y los del régimen de selva (10.5 %). El respaldo a la tasa general vive sólo en la exportación —`_tasa_igv` en [plantilla_excel.py](../../app/services/plantilla_excel.py)— y ahí sí se aplica siempre que falte la tasa, tenga o no tenga IGV el comprobante: los registros reales de contador usados para comparar esta exportación llevan una tasa en todas las filas.

SUNAT manda la tasa como fracción (`0.18`) y el modelo la guarda en puntos, así que [tasa_porcentual](../../app/services/sunat/campos.py) multiplica por 100 — pero solo si el valor es menor que 1. Ese supuesto no está confirmado para el RVIE, y multiplicar a ciegas un `18` que ya viniera en puntos escribiría `1800` en el Excel.
| `extra` | dict | Campos propios del origen que no entran al modelo común. Para `origen="sire"`: `raw_sire` (el JSON crudo de la respuesta, como texto) y `periodo_sunat` (el periodo tributario que asigna SUNAT, que es el que decide a qué registro pertenece el comprobante — no su mes de emisión). En ventas se añaden el CAR SUNAT, el tipo de operación y la referencia al documento que modifica una nota de crédito. |
| `estado_procesamiento` | str | `sire_recibido` → `analizado` \| `error_analisis` \| `sin_datos`. Ver [domain/comprobante.py — EstadoProcesamiento](../../app/domain/comprobante.py). Solo se establece al insertar (`$setOnInsert`); no se pisa en una resincronización. |
| `metadata_procesada` | dict \| None | Salida completa del análisis IA (ver [flujo de análisis](../flujo/05-analisis-ia.md)). |
| `detalle_sunat` | list \| None | Detalle de ítems extraído por scraping (ver [flujo de extracción de detalle](../flujo/04-extraccion-detalle.md)). Ausente hasta que se ejecuta ese job. |

## Por qué `Decimal128` y no `float`

Guardar los montos como `float` reintroduce el problema de precisión que la normalización a `Decimal` existe para evitar (ver los tests de `normalizar_monto` en [tests/domain](../../tests/domain)). Al leer, [monto_a_float](../../app/repositories/_mongo.py:32) convierte a `float` solo en el borde de la serialización JSON, donde la pérdida de precisión ya no importa.

## Índices

- `(empresa_id, periodo)` — consulta general del periodo.
- `uniq_comprobante`, único, sobre `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)` — es la clave de identidad de un comprobante. Este es el índice que reemplaza la deduplicación manual que antes corría en cada arranque: al ser una restricción de unicidad, un upsert nunca inserta el mismo comprobante dos veces.
