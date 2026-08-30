# Endpoints — Comprobantes

Todos bajo `/api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes`.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes`

[listar_comprobantes](../../app/api/v1/routes/comprobantes.py:29). Query params: `libro` (opcional, filtra por `ventas`/`compras`), `limit` (default 100), `skip` (default 0). `404` si el periodo no existe. Devuelve `list[ComprobanteResponse]` — ver [modelo de datos](../modelo-datos/comprobantes.md) para la forma exacta.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes/export`

[exportar_lote](../../app/api/v1/routes/comprobantes.py:45). Exporta hasta 5000 comprobantes del periodo. Query params:

- `formato`: `excel` (por defecto) o `pdf`.
- `libro`: `compras` o `ventas`. **Obligatorio para `formato=excel`** — ese archivo sigue la plantilla oficial de Contasis, que tiene una hoja distinta por libro, así que no hay forma de saber cuál generar; sin él responde `400`. Para `formato=pdf` es un filtro opcional: sin él se exportan los dos libros.

El Excel lo genera [plantilla_excel](../../app/services/plantilla_excel.py) y se llama `registro_{libro}_{periodo}.xlsx`; el PDF lo genera [export_service](../../app/services/export_service.py). `404` si el periodo no tiene comprobantes del libro pedido.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes/{serie_numero}`

[obtener_comprobante](../../app/api/v1/routes/comprobantes.py:75). `serie_numero` es el identificador legible del comprobante (p. ej. `F001-123`), no un `_id` de Mongo.

## `PATCH /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes/{serie_numero}`

[actualizar_comprobante](../../app/api/v1/routes/comprobantes.py:90). Único campo editable: `descripcion`, que se fusiona dentro de `metadata_procesada` (la salida del análisis IA) sin pisar el resto de los campos generados por la IA.

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes/{serie_numero}/export`

[exportar_comprobante](../../app/api/v1/routes/comprobantes.py:112). Query param `formato` (`pdf` por defecto, o `excel`). Exporta un solo comprobante.

Ver también [flujo de consulta y exportación](../flujo/06-consulta-exportacion.md).
