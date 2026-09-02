# Endpoints — Análisis IA

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/analisis`

[ejecutar_analisis](../../app/api/v1/routes/analisis.py:22). Clasifica contablemente, con Gemini, todos los comprobantes del periodo y libro indicados que estén pendientes de análisis (ver [modelo de datos — estado_procesamiento](../modelo-datos/comprobantes.md)). Límite: 5/minuto.

Acepta opcionalmente `archivos` (multipart, uno o más PDFs) como contexto adicional para esa corrida — se indexan al vuelo (chunking + embeddings) y se descartan después, no se guardan como referencia permanente. Si no se envían PDFs, se usa el contexto ya indexado de la empresa (subido previamente vía [referencias](referencias.md)).

`libro` va en la ruta porque el prompt cambia con él: una venta no es un gasto y su contraparte es un cliente, no un proveedor. Ver la tabla de diferencias en el [flujo de análisis con IA](../flujo/05-analisis-ia.md).

El `rubro` que orienta la clasificación **no llega como parámetro del cliente**: se deduce del CIIU dentro del token de SUNAT guardado en la empresa (ver [rubro.py](../../app/domain/rubro.py)).

Respuesta (`StatusResponse`):

```json
{
  "estado": "exito",
  "mensaje": "Análisis completado",
  "datos": {
    "total_encontradas": 10,
    "procesadas": 8,
    "errores": 1,
    "sin_datos": 1,
    "resultados": ["exito", "exito", "error", "sin_datos", "..."]
  }
}
```

`500` si falla la orquestación general (por ejemplo, `GEMINI_API_KEY` no configurada). Fallos por comprobante individual no rompen la corrida: cada uno queda con `estado_procesamiento: error_analisis` y se cuenta en `errores`.

Ver también [flujo de análisis con IA](../flujo/05-analisis-ia.md).
