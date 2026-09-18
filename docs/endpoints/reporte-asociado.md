# Endpoints — Reporte y comprobantes asociados

Bajo `/api/v1/empresas/{ruc}/periodos/{periodo}`. Es la entrega mensual para el contador: un ZIP con el libro conjunto (ventas y compras en formato Contasis, más el control de correlatividad) y los PDFs de ambos registros. Lo arma [reporte_asociado.py](../../app/services/reporte_asociado.py).

## `GET …/reporte-asociado/estado`

`estado_reporte_asociado`. Responde `{"habilitado": bool, "pendientes": n}`. `pendientes` cuenta los comprobantes cuyo estado de glosa es `pendiente` (tipo consultable que todavía no pasó por el portal); los `sin_glosa` y `en_evaluacion` son definitivos y no bloquean. `habilitado` exige además que el periodo tenga comprobantes en algún libro. Ver [glosa y estado](../flujo/05-glosa-y-estado.md).

## `GET …/reporte-asociado`

`descargar_reporte_asociado`. `409` mientras `habilitado` sea falso. Si no, genera el ZIP `<usuario>-<MES><AÑO>.zip` con:

- una hoja **Correlatividad cp**: por registro, emisor, tipo y serie, el rango de números, saltos, duplicados y desorden por fecha del periodo;
- una hoja por libro (**Registro de ventas**, **Registro de compras**) con la plantilla Contasis; cuando un comprobante no tiene glosa, la celda lleva su observación («SUNAT no publica el detalle…», «No se pudo obtener glosa», «Tipo de comprobante en evaluación»);
- los PDFs guardados de los dos registros.

El archivo se escribe en un temporal y se borra al terminar la respuesta.
