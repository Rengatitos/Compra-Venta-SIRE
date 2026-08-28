# Flujo — Consulta y exportación de comprobantes

[comprobante_service.serializar](../../app/services/comprobante_service.py:35) convierte un documento de Mongo a la forma que expone la API: resuelve la descripción legible del tipo de comprobante desde el catálogo ([describe_comprobante](../../app/domain/catalogos.py)), convierte fechas BSON a `date` y montos `Decimal128` a `float` (ver [_mongo.py](../../app/repositories/_mongo.py)), y expone el resultado del análisis IA bajo la clave `analisis` (o `None` si el comprobante aún no fue analizado).

No existe deduplicación al leer: el índice único `uniq_comprobante` (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)) garantiza que un comprobante no pueda insertarse dos veces, así que listar y exportar leen directamente sin filtrar duplicados históricos.

## Exportación

[export_service.py](../../app/services/export_service.py) genera Excel (`excel_de_comprobante`, `excel_de_lote`) y PDF (`pdf_de_comprobante`, `pdf_de_lote`), tanto para un comprobante individual como para un lote completo del periodo. El PDF por lote tiene un límite de 500 comprobantes, como medida de tamaño y tiempo de renderizado.

[_consistencia](../../app/services/export_service.py:47) implementa una heurística: compara la suma de los importes del detalle generado por la IA contra el total real del comprobante, para marcar si ese detalle está completo, fue inferido, o amerita revisión manual antes de confiar en él.

Ver [endpoints — Comprobantes](../endpoints/comprobantes.md) para el detalle de cada endpoint de consulta y exportación.
