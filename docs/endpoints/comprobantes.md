# Endpoints — Comprobantes

Todos bajo `/api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes`, en [routes/comprobantes.py](../../app/api/v1/routes/comprobantes.py). Todas las respuestas de comprobantes pasan por `serializar` ([comprobante_service.py](../../app/services/comprobante_service.py)) y se declaran en `ComprobanteResponse` ([schemas/comprobante.py](../../app/schemas/comprobante.py)); un campo que falte ahí desaparece de la API aunque el Excel lo escriba.

## `GET …/comprobantes`

`listar_comprobantes`. Query params: `libro` (opcional, filtra por `ventas`/`compras`), `limit` (default 100), `skip` (default 0). `404` si el periodo no existe. Devuelve `list[ComprobanteResponse]` — ver [modelo de datos](../modelo-datos/comprobantes.md) para la forma exacta.

Además de los datos del SIRE y los importes, cada fila trae lo que sale del portal SOL y de la glosa:

| Campo | Qué es |
|---|---|
| `glosa` | Texto de la glosa: manual, descripciones del detalle o leyenda del comprobante (ver [glosa y estado](../flujo/05-glosa-y-estado.md)) |
| `estado_glosa` | `con_glosa`, `sin_glosa`, `en_evaluacion` o `pendiente` |
| `observacion` | Por qué no hay glosa: «No se pudo obtener glosa», «SUNAT no publica el detalle de este tipo de comprobante» o «Tipo de comprobante en evaluación». Vacía si hay glosa o está pendiente |
| `detalle_sunat` | Ítems extraídos del portal |
| `leyenda_sunat` | Líneas del recuadro «LEYENDA» del comprobante |
| `pdf_sunat` | Puntero al PDF descargado, o `null` |
| `detraccion`, `detracciones` | Marca de detracción de la propuesta y los NPD asociados |
| `documentos_modificados` | Comprobante que modifica una nota (sólo ventas) |

## `GET …/comprobantes/incompletos`

`incompletos`. Query param `libro` obligatorio. Comprobantes ya consultados en el portal a los que les sigue faltando razón social o documento de la contraparte (`incompleto` en [revision_comprobantes.py](../../app/services/revision_comprobantes.py)). Pensado para ventas, donde el SIRE manda boletas sin receptor y el portal a veces lo completa. La respuesta es el documento crudo más los campos serializados.

## `GET …/comprobantes/anulados-sunat`

`anulados_sunat`. Query param `libro` obligatorio. Comprobantes cuyo detalle del portal dice «anulado»: el Excel los saca de la hoja principal y los lleva a la hoja **Anulados**; el frontend los muestra en su propia vista.

## `GET …/comprobantes/cobertura-sunat`

`cobertura_sunat`. Query param `libro` obligatorio. Cobertura de **todo** el libro en el periodo, independiente de la paginación del listado (`CoberturaSunat`):

```json
{
  "total": 49, "con_detalle": 49, "con_pdf": 49,
  "estado_glosa": {"con_glosa": 49, "sin_glosa": 0, "en_evaluacion": 0, "pendiente": 0}
}
```

Alimenta las tarjetas «Con detalle SOL», «Con PDF guardado» y «Con glosa» de la pantalla de comprobantes.

## `GET …/comprobantes/export`

`exportar_lote`. Exporta hasta 5000 comprobantes del periodo. Query params:

- `formato`: `excel` (por defecto) o `pdf`.
- `libro`: `compras` o `ventas`. **Obligatorio para `formato=excel`** — ese archivo sigue la plantilla oficial de Contasis, que tiene una hoja distinta por libro, así que no hay forma de saber cuál generar; sin él responde `400`. Para `formato=pdf` es un filtro opcional: sin él se exportan los dos libros.
- `destino` (sólo compras): `dg`, `dng`, `dgng` o `auto` (por defecto). Con `auto`, si la empresa sólo tiene ventas exoneradas o inafectas, las compras se llevan a `dng`.

**El Excel de compras reconstruye primero el registro desde el ZIP oficial del ticket RCE** (`sincronizar_ticket_rce`), así que nunca exporta una instantánea vieja de Mongo — y puede cambiar la cantidad de comprobantes del periodo respecto a lo que había. Si el ticket no se puede obtener responde `502`. Después compara cantidad y totales con el resumen oficial y responde `409` si la cantidad no cuadra; `422` si algún comprobante en moneda extranjera no tiene tipo de cambio.

El Excel lo genera [plantilla_excel](../../app/services/plantilla_excel.py) y se llama `registro_{libro}_{periodo}.xlsx`. A la derecha de las columnas de la plantilla añade dos propias, **Observación** y **Estado glosa**, sin desplazar las oficiales (ver [consulta y exportación](../flujo/06-consulta-exportacion.md)). El PDF lo genera [export_service](../../app/services/export_service.py). `404` si el periodo no tiene comprobantes del libro pedido.

## `GET …/comprobantes/conciliacion-rce`

`conciliacion_rce`. Compara las compras guardadas con el resumen oficial del RCE que devuelve el SIRE para el periodo (cantidad de comprobantes y totales por columna) y con el control global. Devuelve las dos cifras y las diferencias ([resumen_rce.py](../../app/services/sunat/resumen_rce.py)). `502` si el SIRE no responde. Es la misma comprobación que hace la exportación a Excel antes de generar el archivo.

## `GET …/comprobantes/{serie_numero}`

`obtener_comprobante`. `serie_numero` es el identificador legible del comprobante (p. ej. `F001-123`), no un `_id` de Mongo. Query param `libro` opcional para desambiguar cuando la misma serie-número existe como venta y como compra.

## `PATCH …/comprobantes/{serie_numero}`

`actualizar_comprobante`. Campos editables: `descripcion`, que se guarda como `glosa` del comprobante sin modificar el detalle SUNAT (y lo deja `con_glosa`), y `razon_social` / `documento_contraparte`, que se guardan como contraparte manual y prevalecen sobre lo que trajo el SIRE.

## `GET …/comprobantes/{serie_numero}/export`

`exportar_comprobante`. Query param `formato` (`pdf` por defecto, o `excel`). Exporta un solo comprobante.

Ver también [flujo de consulta y exportación](../flujo/06-consulta-exportacion.md).
