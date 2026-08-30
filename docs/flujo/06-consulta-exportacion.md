# Flujo — Consulta y exportación de comprobantes

[comprobante_service.serializar](../../app/services/comprobante_service.py:35) convierte un documento de Mongo a la forma que expone la API: resuelve la descripción legible del tipo de comprobante desde el catálogo ([describe_comprobante](../../app/domain/catalogos.py)), convierte fechas BSON a `date` y montos `Decimal128` a `float` (ver [_mongo.py](../../app/repositories/_mongo.py)), y expone el resultado del análisis IA bajo la clave `analisis` (o `None` si el comprobante aún no fue analizado).

No existe deduplicación al leer: el índice único `uniq_comprobante` (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)) garantiza que un comprobante no pueda insertarse dos veces, así que listar y exportar leen directamente sin filtrar duplicados históricos.

## Exportación

Hay dos salidas con propósitos distintos:

- **Excel por lote** — [plantilla_excel.excel_plantilla](../../app/services/plantilla_excel.py). Es el entregable contable: reproduce el formato oficial «REGISTRO DE COMPRAS Y VENTAS» de Contasis, un archivo por libro.
- **PDF** y **Excel de un comprobante** — [export_service.py](../../app/services/export_service.py) (`pdf_de_lote`, `pdf_de_comprobante`, `excel_de_comprobante`). Son las salidas de revisión, y **las únicas que llevan el análisis IA**. El PDF por lote tiene un límite de 500 comprobantes, como medida de tamaño y tiempo de renderizado.

### El formato de la plantilla

La plantilla real vive en [app/resources/plantilla_registro.xlsx](../../app/resources/plantilla_registro.xlsx). Es una copia de `source/PLANTILLA REGISTRO DE COMPRAS Y VENTAS.xlsx`, que está fuera del control de versiones y por tanto no llega a la imagen de Docker; dentro de `app/` sí, porque el [Dockerfile](../../Dockerfile) copia ese directorio entero.

No se reconstruye el layout a mano: se abre el archivo y se escriben las filas debajo de sus encabezados. Las filas 1–13 (notas de uso, título y los tres niveles de encabezado) se conservan intactas; las filas de ejemplo que trae la plantilla —con fórmulas como `=+A14` o `=+S14/1.18`— se borran junto con su pie de totales, y se reescribe un pie que suma el rango real de datos. Cada fila nueva hereda el estilo de la fila 14 original (bordes, formato contable), salvo las columnas de fecha, que se fuerzan al `dd/mm/yyyy` que documenta la propia fila 13 de la plantilla.

**El análisis IA no entra en este archivo.** Las columnas `CUENTA CONTABLE …` y `GLOSA` existen en el formato pero se dejan vacías: hoy solo podría llenarlas la IA, y se decidió llenarlas en un trabajo posterior. Tampoco quedan vacías por descuido `CONDICION CONTADO/CREDITO` ni las columnas de referencia al comprobante que se modifica (las notas de crédito y débito deberían apuntar al original): ese dato está dentro de `extra.raw_sire` pero todavía no se mapea al modelo de dominio.

El libro de ventas está mapeado por completo, pero [propuesta.descargar](../../app/services/sunat/propuesta.py:99) todavía rechaza `ventas` (el RVIE no tiene cliente HTTP), así que hasta entonces esa exportación responde `404`.

Ver [endpoints — Comprobantes](../endpoints/comprobantes.md) para el detalle de cada endpoint de consulta y exportación.
