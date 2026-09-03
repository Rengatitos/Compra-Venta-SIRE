# Flujo — Sincronización de la propuesta SIRE

[POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta](../endpoints/propuesta.md) llama a [propuesta_service.sincronizar](../../app/services/propuesta_service.py:16).

## Pasos

1. La empresa ya llegó resuelta y verificada por la dependencia [empresa_actual](../../app/api/v1/deps.py:9) — la ruta no vuelve a buscarla.

2. Los dos libros siguen el mismo camino. [sunat/propuesta.py](../../app/services/sunat/propuesta.py) se queda con el transporte —URL, credenciales, paginación— y delega el mapeo de campos en [sunat/rce.py](../../app/services/sunat/rce.py) (compras) o [sunat/rvie.py](../../app/services/sunat/rvie.py) (ventas), que son los que conocen los nombres de cada libro.

   Cada libro tiene su endpoint, y **no se llaman igual**:

   | Libro | Endpoint | Parámetros |
   |---|---|---|
   | Compras (RCE) | `…/libros/rce/propuesta/web/propuesta/{periodo}/busqueda` | `page`, `perPage`, `codTipoOpe=1` |
   | Ventas (RVIE) | `…/libros/rvie/propuesta/web/propuesta/{periodo}/comprobantes` | `page`, `perPage` |

   El RVIE **no** tiene `/busqueda` ni `/preliminar`: responden `500`. Su único otro camino es `exportapropuesta`, que devuelve un `numTicket` y obliga al flujo asíncrono; no hace falta, porque `/comprobantes` da los mismos datos de forma directa.

3. `descargar` resuelve las credenciales OAuth con [credenciales_cliente](../../app/services/sunat/auth.py:24): usa las propias de la empresa si existen, o cae a las variables de entorno globales.

4. **Manejo del token OAuth**, en [peticion_autenticada](../../app/services/sunat/auth.py:87). Si la empresa no tiene un token guardado, se pide uno nuevo con [obtener_token](../../app/services/sunat/auth.py:32) — una petición tipo `password` contra el servicio de seguridad de SUNAT, usando como username la concatenación directa de RUC y usuario SOL sin separador (formato exigido por SUNAT). Luego se llama a la API SIRE con la plantilla del libro, reemplazando el placeholder de periodo. Los dos endpoints devuelven la misma forma —`{paginacion: {page, perPage, totalRegistros}, registros: [...], totales: {...}}`— y los dos exigen `page` y `perPage`: omitirlos da `422` nombrando el campo que falta.

La respuesta se recorre **página a página** hasta agotar `totalRegistros` o hasta que una página venga corta, con `SIRE_MAX_PAGINAS` como freno por si el endpoint ignorase `page`. Antes se pedía `page=1&perPage=100` fijo y todo lo que pasara de cien comprobantes se perdía sin que nada lo dijera; en ventas eso ocurre casi siempre. `perPage` no puede pasar de 100 (por encima, `422`), así que se recorta. `codTipoOpe=1` sólo se manda en compras: el RVIE lo acepta pero lo ignora.

El bloque `totales` que acompaña a cada respuesta es el mejor control del mapeo: sus sumas tienen que cuadrar con las de los comprobantes ya mapeados. Si la respuesta es `401` (token expirado), se llama a [renovar_token](../../app/services/sunat/auth.py:64) y se reintenta la misma petición una vez. Si no hay credenciales de cliente disponibles y el token expiró, se lanza `ErrorSunat` en vez de reintentar sin credenciales.

5. **Mapeo al modelo canónico**, en el `a_comprobante` del módulo del libro. Cada registro crudo de SUNAT se convierte a un `Comprobante` normalizado (ver [modelo de datos de comprobantes](../modelo-datos/comprobantes.md)). Los nombres de campo se resuelven probando una lista de candidatos por cada destino (serie, número, tipo, montos, etc.) — la respuesta real de SUNAT no está confirmada al 100% contra la documentación oficial, así que el mapeo tolera variaciones de nombre. El JSON crudo completo se conserva en `extra.raw_sire`.

   Los montos llegan en un bloque anidado `montos` con los nombres del RCE, que no son los que sugiere la documentación:

   | Campo del modelo | Campo del SIRE |
   |---|---|
   | `base_imponible` | suma de `mtoBIGravadaDG` + `mtoBIGravadaDGNG` + `mtoBIGravadaDNG` |
   | `igv` | suma de `mtoIgvIpmDG` + `mtoIgvIpmDGNG` + `mtoIgvIpmDNG` |
   | `no_gravado` | `mtoValorAdqNG` |
   | `icbper` | `mtoIcbp` |
   | `isc` | `mtoISC` |
   | `otros_tributos` | `mtoOtrosTrib` |
   | `total` | `mtoTotalCp` |

   La base y el IGV **se suman** entre los tres destinos (gravadas, gravadas y no gravadas, no gravadas) porque un comprobante puede traer importe en más de uno. Los campos `...Original` guardan el valor previo a una modificación y no entran en la suma.

   Además de la suma, cada destino se guarda por separado en `base_imponible_dg`/`dgng`/`dng` y `igv_dg`/`dgng`/`dng`: el registro de compras los pide en columnas distintas, así que la suma sola no basta para exportar (ver [modelo de datos](../modelo-datos/comprobantes.md)).

   El vencimiento llega en `fecVencPag`. Con los otros dos nombres que se probaban antes el campo salía siempre vacío y el Excel acababa repitiendo la fecha de emisión. La tasa de IGV viene como fracción (`0.18`) en `porTasaIGV` y se guarda en puntos porcentuales; si no viene, se guarda `None` en vez de la tasa general, para no falsear los comprobantes no gravados ni los del régimen de selva.

   El RVIE usa otros nombres y otra estructura: manda los importes sueltos en la raíz, separa exonerado de inafecto (el RCE los agrupa en «adquisiciones no gravadas») y trae los descuentos en columna aparte.

   | Campo del modelo | Campo del SIRE (RVIE) |
   |---|---|
   | `base_imponible` | `mtoBIGravada` − `mtoDsctoBI` |
   | `igv` | `mtoIgvIpm` − `mtoDsctoIgvIpm` |
   | `exonerado` | `mtoExonerado` |
   | `inafecto` | `mtoInafecto` |
   | `otros_tributos` | `mtoOtrosTributos` + `mtoIvap` |
   | `total` | `mtoTotalCP` |

   Los descuentos llegan en positivo: sin restarlos, la base y el IGV de cualquier venta con descuento salen por encima de lo declarado. Ojo con el nombre: el descuento del IGV es `mtoDsctoIGV`, no el `mtoDsctoIgvIpm` que sugeriría la simetría con el RCE.

   **La contraparte es el punto delicado.** El registro trae dos razones sociales: `nomRazonSocial`, que es la de la **propia empresa emisora**, y `nomRazonSocialCliente`, que es la del cliente. Tomar la primera ponía el nombre del vendedor en todas y cada una de las filas del registro de ventas.

   Otras dos diferencias con el RCE: el RVIE manda los importes **sueltos en la raíz**, sin bloque `montos`, y no trae ni fecha de vencimiento (`fecVencPag`) ni tasa de IGV (`porTasaIGV`). Sin tasa, el comprobante queda con `porcentaje_igv=None` y la exportación cae en la tasa general, tenga o no tenga IGV el comprobante.

   Lo que no cabe en el modelo común —`mtoValFactExpo`, `mtoBIIvap`, `codCar`, `indTipoOperacion`, `codEstadoComprobante`, las operaciones gratuitas y el `documentoMod` al que apunta una nota de crédito— va a `extra`.

   Este mapeo estuvo equivocado: se buscaban `mtoBIGravada` y `mtoIGV`, nombres que el SIRE no envía nunca, así que la base imponible y el IGV llegaban siempre en cero y sólo el total era correcto. Los tests usaban un payload inventado con esos mismos nombres, así que pasaban en verde. El fixture de `tests/domain/test_mapeo.py` es ahora una respuesta real. Para recalcular comprobantes ya guardados sin volver a llamar a SUNAT existe [scripts/recalcular_importes.py](../../scripts/recalcular_importes.py), que rehace los montos desde `extra.raw_sire`.

6. **Dos filtros**, aplicados en [propuesta_service.sincronizar](../../app/services/propuesta_service.py:16):
   - `comprobante.es_valido`: descarta filas sin serie, número o fecha de emisión.
   - `pertenece_al_periodo`: el **periodo tributario que asigna SUNAT** (`perTributario` en el RCE, `perPeriodoTributario` en el RVIE, guardado en `extra.periodo_sunat`) debe coincidir con el solicitado.

   Este filtro comparaba antes la **fecha de emisión**, dando por hecho que SUNAT devolvía comprobantes de periodos vecinos por descuido. No era así: los devuelve porque pertenecen al periodo pedido. Una factura emitida en julio y anotada en agosto entra en el registro de agosto —el crédito fiscal del IGV no caduca ese mes— y llega con `perTributario=202608`. Comparar por emisión la descartaba: en un periodo real eran 27 de 87 compras, S/ 3.101,89 con su crédito, y lo único que lo delataba era el contador de `descartados`. Si el campo faltara, se cae al mes de emisión, que es lo único que quedaría.

   Había un tercer filtro, `serie_aceptada`, que sólo dejaba pasar series `F` y `E` y por tanto tiraba las boletas. El registro de ventas es en su mayoría boletas (`B001`, `EB01`), así que desapareció de los dos libros: ahora se guarda todo lo que SUNAT devuelve.

7. **Persistencia**, vía [repo_comprobantes.upsert](../../app/repositories/comprobantes.py:110). El filtro de identidad es `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)`. Los campos de identidad y el `estado_procesamiento` inicial solo se establecen si el documento es nuevo (`$setOnInsert`); el resto de los campos (contraparte, montos, datos crudos) se actualizan siempre, para que una resincronización refresque los datos sin perder el avance del análisis IA ya hecho.

8. Si SUNAT responde `422`, se interpreta como "sin propuestas para ese periodo" — no es un error: el periodo se marca `sin_propuesta` y se devuelve `nuevos: 0`. Si la sincronización tiene éxito (con o sin comprobantes nuevos), el periodo se marca `sincronizado`.

Ver [modelo de datos de comprobantes](../modelo-datos/comprobantes.md) para el detalle completo de los campos que este proceso escribe, y [flujo de extracción de detalle](04-extraccion-detalle.md) para el paso opcional siguiente.
