# Endpoints — Propuesta SIRE

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta`

[sincronizar_propuesta](../../app/api/v1/routes/propuesta.py:19). Descarga la propuesta de comprobantes del SIRE para el periodo y libro indicados, la normaliza al modelo canónico y la guarda vía upsert. Límite: 10/minuto.

**`libro` acepta `ventas` o `compras`, pero solo `compras` está implementado.** Con `libro=ventas` el endpoint responde `501 Not Implemented` con un mensaje explícito — el libro de ventas (RVIE) todavía no tiene cliente HTTP. Ver [propuesta_service.py](../../app/services/propuesta_service.py) y [sunat/propuesta.py](../../app/services/sunat/propuesta.py).

Respuesta (`StatusResponse`):

```json
{
  "estado": "exito",
  "mensaje": "Se sincronizaron 12 comprobantes",
  "datos": {"nuevos": 8, "actualizados": 4, "descartados": 3}
}
```

`descartados` cuenta comprobantes que llegaron en la respuesta de SUNAT pero no pasaron alguno de los tres filtros: fila inválida (sin serie/número/fecha), serie fuera del prefijo aceptado (ver más abajo), o fecha de emisión fuera del periodo solicitado.

Errores:

- `502` si la API SIRE responde con un error no controlado, o si no se pudo renovar el token OAuth.
- Si SUNAT responde `422` (sin propuesta para el periodo), **no es un error**: se guarda el periodo como `sin_propuesta` y se devuelve `nuevos: 0`.

## Limitación heredada: filtro de series

La sincronización solo registra comprobantes cuya serie empiece con `F` o `E` (facturas y recibos por honorarios). Boletas y otros tipos de comprobante se descartan silenciosamente en el conteo de `descartados`. Ver `PREFIJOS_SERIE_ACEPTADOS` en [sunat/propuesta.py](../../app/services/sunat/propuesta.py:16).

Ver también [flujo de sincronización de la propuesta](../flujo/03-sincronizacion-propuesta.md).
