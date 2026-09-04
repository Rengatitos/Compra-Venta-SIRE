# Flujo — Consulta y exportación de comprobantes

[comprobante_service.serializar](../../app/services/comprobante_service.py:35) convierte un documento de Mongo a la forma que expone la API: resuelve la descripción legible del tipo de comprobante desde el catálogo ([describe_comprobante](../../app/domain/catalogos.py)), convierte fechas BSON a `date` y montos `Decimal128` a `float` (ver [_mongo.py](../../app/repositories/_mongo.py)), y expone el resultado del análisis IA bajo la clave `analisis` (o `None` si el comprobante aún no fue analizado).

No existe deduplicación al leer: el índice único `uniq_comprobante` (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)) garantiza que un comprobante no pueda insertarse dos veces, así que listar y exportar leen directamente sin filtrar duplicados históricos.

## Exportación

Hay dos salidas con propósitos distintos:

- **Excel por lote** — [plantilla_excel.excel_plantilla](../../app/services/plantilla_excel.py). Es el entregable contable: reproduce el formato oficial «REGISTRO DE COMPRAS Y VENTAS» de Contasis, un archivo por libro.
- **PDF** y **Excel de un comprobante** — [export_service.py](../../app/services/export_service.py) (`pdf_de_lote`, `pdf_de_comprobante`, `excel_de_comprobante`). Son las salidas de revisión y llevan el análisis IA completo. El PDF por lote tiene un límite de 500 comprobantes, como medida de tamaño y tiempo de renderizado.

### El formato de la plantilla

La plantilla real vive en [app/resources/plantilla_registro.xlsx](../../app/resources/plantilla_registro.xlsx), generada por [scripts/preparar_plantilla.py](../../scripts/preparar_plantilla.py) a partir de `source/PLANTILLA REGISTRO DE COMPRAS Y VENTAS.xlsx`, que está fuera del control de versiones y por tanto no llega a la imagen de Docker; dentro de `app/` sí, porque el [Dockerfile](../../Dockerfile) copia ese directorio entero.

No se reconstruye el layout a mano: se abre el archivo y se escriben las filas debajo de sus encabezados. La plantilla oficial de Contasis trae trece filas de notas de uso, título y especificación antes del encabezado, y letra y columnas tan chicas que el propio encabezado se cortaba; ningún registro real de contador las conserva. `scripts/preparar_plantilla.py` las quita: el encabezado de tres niveles queda en las filas 1–3, negrita sobre azul, y los datos empiezan en la fila 4, que además sirve de prototipo de estilo (bordes, formato contable, fuente). Cada fila nueva hereda ese estilo, salvo las columnas de fecha, que se fuerzan al `dd/mm/yyyy` que documentaba la especificación original, y salvo la altura, que la resuelve la propia plantilla (`defaultRowHeight`) en vez de fijarse fila por fila. Al final se reescribe un único pie `TOTAL` que suma el rango real de datos.

### Qué del análisis IA llega al archivo

De la clasificación viajan la **cuenta contable** y la **glosa**, en mayúsculas —así las escriben los contadores en los registros reales usados para comparar esta exportación—. Cuando el clasificador RAG ([ollama_rag.py](../../app/services/ollama_rag.py)) resolvió una cuenta o una glosa propias para la empresa, ganan a las del análisis general; si no, la glosa sale del nombre del único ítem cuando el comprobante tiene uno solo —que es la mejor descripción posible y casi siempre cabe— y de la descripción resumida del análisis cuando tiene varios. En ambos casos se recorta a los 60 caracteres que declaraba la plantilla original (`MAX_GLOSA`), cortando por palabra: Contasis trunca por su cuenta al importar, y el corte cae donde caiga.

El **centro de costos** no viaja, aunque la IA lo devuelva: la plantilla pide el *código* del catálogo de Contasis y el modelo devuelve un nombre descriptivo. Escribirlo recortado inventaría códigos que colisionan entre sí.

### Columnas que se llenan con una regla, y lo que sigue vacío

Tres columnas no vienen de SUNAT ni del análisis, sino de una regla, porque así aparecen en el 100 % de los registros reales de contador usados para comparar esta exportación:

- **CONDICION CONTADO/CREDITO** — `CRE` cuando hay un vencimiento posterior a la emisión, si no `CON`. Es una heurística a partir de las fechas (`_condicion_pago` en [plantilla_excel.py](../../app/services/plantilla_excel.py)): acertó en torno al 92 % de las compras de uno de los clientes usados para compararla, así que no reemplaza el criterio de un contador en los casos límite.
- **CUENTA CONTABLE TOTAL** — la que resolvió el RAG para la empresa (`rag.cuenta_total`) o, si no hay, la general del libro: `4212` en compras, `1212` en ventas (PCGE 42.1.2 / 12.1.2).
- **PORCENTAJE I.G.V.** — la tasa declarada o, si no vino, la general; siempre tiene valor, también en las operaciones sin IGV.

La **referencia al comprobante que modifica una nota de crédito o débito** (fecha, tipo, serie y número) sólo se llena en ventas, desde `extra.documentos_modificados` (lo que manda `documentoMod` del RVIE); el RCE nunca lo manda, así que esas columnas quedan siempre vacías en compras.

### El registro se lleva en soles

SUNAT devuelve cada comprobante en la moneda en que se emitió, así que un periodo real trae soles y dólares mezclados. Los cuatro registros reales de contador usados para comparar esta exportación no dejan cada fila en su moneda: convierten todo a soles con el tipo de cambio de la propia fila, y el importe original en dólares va aparte, en «EQUIVALENTE EN DOLARES AMERICANOS» (AC en compras, W en ventas). La columna MONEDA conserva la letra —`S` o `D`— y el tipo de cambio (4 decimales: la plantilla lo declara `(10,4)` y a dos decimales un `3.387` se convertía en `3.39`) sólo se escribe en las filas que están en moneda extranjera; en soles se queda vacía.

Una fila en moneda extranjera **sin** tipo de cambio no se puede convertir: se deja el importe nominal, marcado con el símbolo de su moneda (`US$` o el código ISO) para que se note que, a diferencia del resto, no está en soles. Es la misma situación que ya distinguía `sin_tipo_cambio` en el dashboard (ver más abajo); ahora el Excel y el dashboard coinciden en el criterio.

Con todo en una sola moneda, el pie de totales vuelve a ser una única fila `TOTAL` con `=SUM(...)` por columna, sin `SUMIF` ni un pie por moneda.

En el **dashboard**, los agregados de `analytics_service` (`get_summary`, `get_top_contrapartes`) ya convertían a soles multiplicando cada importe por el tipo de cambio del propio comprobante antes de sumarlos, y un comprobante sin tipo de cambio se sumaba por su valor nominal (contado aparte en `sin_tipo_cambio`). Es la misma regla que ahora sigue el Excel: el «Monto total» del dashboard y el registro exportado se llevan igual.

### Las columnas de base e IGV en compras

El registro de compras pide la base y el IGV **repartidos por destino** —gravadas en J/K, gravadas y no gravadas en L/M, no gravadas en N/O— y no el total en una sola columna. Por eso la exportación usa el desglose `base_imponible_dg`/`dgng`/`dng` en vez de `base_imponible`, que es su suma: mandarlo todo a J/K declararía como gravado lo destinado a operaciones no gravadas. La hoja de ventas no tiene ese reparto, porque el RVIE no lo hace.

Los dos libros están mapeados y los dos se sincronizan, así que ambas exportaciones tienen datos. El `404` queda reservado a su caso real: pedir un libro que ese periodo no tiene.

Ver [endpoints — Comprobantes](../endpoints/comprobantes.md) para el detalle de cada endpoint de consulta y exportación.
