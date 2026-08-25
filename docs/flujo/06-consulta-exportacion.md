# Flujo — Consulta y exportación de facturas

[serialize_factura](../../app/services/invoice_service.py:34) combina los campos "crudos" que llegan de SIRE (identificador de referencia, RUC del emisor, etc.) con el resultado del análisis con IA, que puede estar guardado como objeto o como texto JSON según qué ruta lo haya escrito por última vez. [parse_metadata](../../app/services/invoice_service.py:19) normaliza ambas representaciones para que el resto del sistema no tenga que preocuparse por cuál de las dos está presente.

[dedupe_by_reference](../../app/services/invoice_service.py:7) conserva solo el primer registro por identificador de referencia al listar o exportar facturas, como defensa adicional ante duplicados históricos que aún no hayan sido limpiados por la deduplicación de arranque (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)).

## Exportación

El servicio de exportación genera Excel (con [generate_excel_from_invoice](../../app/services/export_service.py:58) y [generate_excel_from_invoices_batch](../../app/services/export_service.py:199)) y PDF (con [generate_pdf_from_invoice](../../app/services/export_service.py:81) y [generate_pdf_from_invoices_batch](../../app/services/export_service.py:252)), tanto para una factura individual como para un lote completo del periodo. El PDF por lote tiene un límite de 500 facturas, como medida de seguridad de tamaño y tiempo de renderizado.

[_consistency_label](../../app/services/export_service.py:30) implementa una heurística de consistencia: compara la suma de los importes del detalle generado por la IA contra el total real del comprobante, para marcar visualmente si ese detalle es completo, si fue inferido, o si amerita revisión manual antes de confiar en él.

Ver [endpoints — Invoices](../endpoints/invoices.md) para el detalle de cada endpoint de consulta y exportación.
