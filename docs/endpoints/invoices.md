# Endpoints — Invoices

Prefijo `/sol-users/{user_id}/periodos/{periodo}/facturas`, montado en [main.py](../../app/main.py:132). Router en [invoices.py](../../app/api/routes/invoices.py).

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/` | [list_invoices](../../app/api/routes/invoices.py:25) | require_same_user |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/export/batch` y `/facturas/batch/export` | [export_invoices_batch](../../app/api/routes/invoices.py:40) | require_same_user |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}` | [get_invoice](../../app/api/routes/invoices.py:72) | require_same_user |
| PATCH | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}` | [update_invoice](../../app/api/routes/invoices.py:87) | require_same_user |
| GET | `/sol-users/{user_id}/periodos/{periodo}/facturas/{id_factura}/export` | [export_invoice](../../app/api/routes/invoices.py:112) | require_same_user |

**list_invoices** lista, de forma paginada, las facturas del periodo, deduplicadas por su identificador de referencia (ver [modelo de datos de facturas](../modelo-datos/facturas.md)).

**export_invoices_batch** exporta todas las facturas del periodo (hasta 5000) en formato Excel o PDF. Las dos rutas listadas apuntan exactamente a la misma función; el alias existe por compatibilidad con distintas versiones de los clientes que consumen esta API.

**get_invoice** devuelve el detalle de una factura, identificada por su combinación de serie y número.

**update_invoice** actualiza el campo de descripción dentro de los datos ya procesados por la IA, preservando si ese bloque estaba guardado como texto JSON o como objeto (ver la nota sobre esta doble representación en [modelo de datos de facturas](../modelo-datos/facturas.md)).

**export_invoice** exporta una factura individual, en formato PDF por defecto o en Excel.

El detalle del proceso de exportación (generación de Excel y PDF, y la heurística de consistencia entre el detalle generado por la IA y el total real del comprobante) está en [flujo de consulta y exportación](../flujo/06-consulta-exportacion.md).
