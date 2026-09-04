# Endpoints — Auditoría

## `GET /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/auditoria/reporte`

[obtener_reporte](../../app/api/v1/routes/auditoria.py:118). La tabla comparativa que pide el auditor.

El auditor pide tres cosas. Dos ya existían: la **glosa detallada** la produce el RAG ([ollama_rag.py](../../app/services/ollama_rag.py)) y los **PDFs en ZIP** los sirve [pdfs.md](pdfs.md). Este endpoint arma la tercera: la tabla comparativa **con fuentes**.

Lo que la hace un reporte de auditoría y no un listado más es el bloque `fuentes`: por cada comprobante dice de dónde salió cada dato. Sin eso no se puede distinguir un importe que declaró SUNAT en la propuesta de uno que se leyó del portal o del PDF, que es justo lo que hay que poder rastrear.

```json
{
  "periodo": "202504",
  "libro": "compras",
  "resumen": {
    "comprobantes": 17, "con_pdf": 0, "con_detalle": 16, "con_glosa": 7,
    "comparables": 16, "descuadrados": 3, "total_registro": 3276.52
  },
  "zip_disponible": false,
  "filas": [
    {
      "serie_numero": "F001-57113",
      "total": 107.43,
      "importe_detalle": 107.48,
      "diferencia": 0.05,
      "lineas_detalle": 3,
      "glosa": "Adquisición de bebidas embotelladas …",
      "cuenta_base": "6011",
      "fuentes": ["propuesta_sire", "detalle_portal_sol"],
      "pdf": null
    }
  ]
}
```

### La columna comparable

`importe_detalle` es la suma de la columna `valor_venta` de las líneas que el scraper leyó del portal (`_COLUMNAS` en [scraping_sunat.py](../../app/services/scraping_sunat.py)). Contra los datos reales esa suma cuadra con `total` al céntimo, así que las diferencias que aparecen son de verdad: en un periodo real salieron tres, de S/ 0.05, S/ 0.10 y S/ 0.05.

**`importe_detalle` y `diferencia` van en `null` cuando no hay ninguna línea con importe legible.** Eso **no** es un cero: significa que no hay con qué comparar. La distinción es la que sostiene el reporte —confundirlas hacía que todo comprobante con detalle saliera descuadrado por su importe completo— y es también por lo que el resumen separa `comparables` de `descuadrados`: «0 descuadrados» sobre 0 comparables no dice nada, y presentarlo como si todo cuadrara sería mentir.

La tolerancia del descuadre es de un céntimo. No es arbitraria: el registro reporta dos decimales y las líneas del portal se suman una a una, así que sin tolerancia nada cuadraría nunca.

### Las fuentes

De menos a más cerca del documento original:

| Fuente | Significado |
|---|---|
| `propuesta_sire` | El comprobante entró por la propuesta del SIRE: es lo que lo hizo existir |
| `detalle_portal_sol` | Tiene el detalle de ítems raspado del portal ([detalle.md](detalle.md)) |
| `pdf_descargado` | Tiene el PDF guardado en el servidor ([pdfs.md](pdfs.md)) |

Un comprobante recién sincronizado sólo cita `propuesta_sire`; las otras dos se suman a medida que se recolectan. Un comprobante de origen `contasis` no cita la propuesta, porque no salió de ahí.

`zip_disponible` dice si hay algo que descargar, para no ofrecer un botón que va a responder `404`.

`404` si el periodo no existe para la empresa. `limit` tope 5000, el mismo que usa la exportación a Excel.

## Fuera de alcance hoy

Los **campos de auditoría** (a qué se usó cada comprobante, por qué y para qué) todavía no están: el cliente no los ha especificado. Construir un formulario con campos inventados sería trabajo que habría que tirar.
