# Flujo — Consulta y exportación de comprobantes

[comprobante_service.serializar](../../app/services/comprobante_service.py:35) convierte un documento de Mongo a la forma que expone la API: resuelve la descripción legible del tipo de comprobante desde el catálogo ([describe_comprobante](../../app/domain/catalogos.py)), convierte fechas BSON a `date` y montos `Decimal128` a `float` (ver [_mongo.py](../../app/repositories/_mongo.py)), y expone el resultado del análisis IA bajo la clave `analisis` (o `None` si el comprobante aún no fue analizado).

No existe deduplicación al leer: el índice único `uniq_comprobante` (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)) garantiza que un comprobante no pueda insertarse dos veces, así que listar y exportar leen directamente sin filtrar duplicados históricos.

## Exportación

Hay dos salidas con propósitos distintos:

- **Excel por lote** — [plantilla_excel.excel_plantilla](../../app/services/plantilla_excel.py). Es el entregable contable: reproduce el formato oficial «REGISTRO DE COMPRAS Y VENTAS» de Contasis, un archivo por libro.
- **PDF** y **Excel de un comprobante** — [export_service.py](../../app/services/export_service.py) (`pdf_de_lote`, `pdf_de_comprobante`, `excel_de_comprobante`). Son las salidas de revisión y llevan el análisis IA completo. El PDF por lote tiene un límite de 500 comprobantes, como medida de tamaño y tiempo de renderizado.

### El formato de la plantilla

La plantilla real vive en [app/resources/plantilla_registro.xlsx](../../app/resources/plantilla_registro.xlsx). Es una copia de `source/PLANTILLA REGISTRO DE COMPRAS Y VENTAS.xlsx`, que está fuera del control de versiones y por tanto no llega a la imagen de Docker; dentro de `app/` sí, porque el [Dockerfile](../../Dockerfile) copia ese directorio entero.

No se reconstruye el layout a mano: se abre el archivo y se escriben las filas debajo de sus encabezados. Las filas 1–13 (notas de uso, título y los tres niveles de encabezado) se conservan intactas; las filas de ejemplo que trae la plantilla —con fórmulas como `=+A14` o `=+S14/1.18`— se borran junto con su pie de totales, y se reescribe un pie que suma el rango real de datos. Cada fila nueva hereda el estilo de la fila 14 original (bordes, formato contable), salvo las columnas de fecha, que se fuerzan al `dd/mm/yyyy` que documenta la propia fila 13 de la plantilla.

### Qué del análisis IA llega al archivo

De la clasificación viajan dos columnas: la **cuenta contable** y la **glosa**. La glosa sale del nombre del único ítem cuando el comprobante tiene uno solo —que es la mejor descripción posible y casi siempre cabe— y de la descripción resumida del análisis cuando tiene varios; en ambos casos recortada al ancho que declara la fila 13, cortando por palabra. Contasis trunca por su cuenta al importar, y el corte cae donde caiga.

El **centro de costos** no viaja, aunque la IA lo devuelva: la plantilla pide el *código* del catálogo de Contasis y el modelo devuelve un nombre descriptivo. Escribirlo recortado inventaría códigos que colisionan entre sí.

### Lo que sigue vacío

`CONDICION CONTADO/CREDITO` y las columnas de referencia al comprobante que se modifica (las notas de crédito y débito deberían apuntar al original) quedan vacías: ese dato está dentro de `extra.raw_sire` pero todavía no se mapea al modelo de dominio.

### Soles y dólares en el mismo registro

SUNAT devuelve cada comprobante en la moneda en que se emitió, así que un periodo real trae las dos mezcladas. El formato Contasis las distingue con una letra —`S` o `D`— en la columna MONEDA (AB en compras, V en ventas), pero eso queda a treinta columnas de los importes y no ayuda a leerlos.

Por eso las columnas de dinero llevan el **símbolo de su fila** en el formato de celda: `S/ 1,234.00` o `US$ 1,234.00`. Es sólo formato —el valor de la celda sigue siendo un número, así que la importación a Contasis no cambia—, pero resuelve de golpe las dos confusiones: que un número pelado no se leía como importe, y que no se sabía en qué moneda estaba. Una moneda que no sea PEN ni USD se queda con el formato contable sin símbolo, en vez de inventarle uno.

El tipo de cambio y el porcentaje de IGV **no** llevan símbolo: no son dinero. El tipo de cambio además se redondea a cuatro decimales, no a dos, porque la plantilla lo declara `(10,4)` y a dos un `3.387` se convertía en `3.39`.

El pie de totales es **uno por moneda** (`TOTAL S/`, `TOTAL US$`), resuelto con `SUMIF` sobre la columna MONEDA. Antes había una sola fila que sumaba soles y dólares en la misma celda: un número que no significa nada. Con una única moneda en el periodo se mantiene la suma simple que espera la plantilla.

En el **dashboard** la decisión es la contraria, y por un motivo: ahí no hay filas, hay un número por métrica. Los agregados de `analytics_service` (`get_summary`, `get_top_contrapartes`) **convierten a soles** multiplicando cada importe por el tipo de cambio del propio comprobante —el que SUNAT declaró para esa operación— antes de sumarlos, que es como se lleva el registro. Un comprobante en moneda extranjera sin tipo de cambio no se puede convertir: se suma por su valor nominal, para no descuadrar el total contra el número de comprobantes, y se cuenta en `sin_tipo_cambio` para que el dashboard avise de que la cifra se queda corta.

Por eso el «Monto total» del dashboard no coincide con la suma de la columna del listado, donde cada comprobante conserva su moneda. La nota de cada métrica lo dice.

### Las columnas de base e IGV en compras

El registro de compras pide la base y el IGV **repartidos por destino** —gravadas en J/K, gravadas y no gravadas en L/M, no gravadas en N/O— y no el total en una sola columna. Por eso la exportación usa el desglose `base_imponible_dg`/`dgng`/`dng` en vez de `base_imponible`, que es su suma: mandarlo todo a J/K declararía como gravado lo destinado a operaciones no gravadas. La hoja de ventas no tiene ese reparto, porque el RVIE no lo hace.

La columna de tasa usa la que declaró SUNAT (`porcentaje_igv`). El 18 % general solo entra como respaldo cuando el comprobante **tiene** IGV y no vino la tasa; sin IGV la celda se queda vacía en vez de afirmar una tasa que no corresponde.

Los dos libros están mapeados y los dos se sincronizan, así que ambas exportaciones tienen datos. El `404` queda reservado a su caso real: pedir un libro que ese periodo no tiene.

Ver [endpoints — Comprobantes](../endpoints/comprobantes.md) para el detalle de cada endpoint de consulta y exportación.
