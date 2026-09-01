# Endpoints — Propuesta SIRE

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta`

[sincronizar_propuesta](../../app/api/v1/routes/propuesta.py:19). Descarga la propuesta de comprobantes del SIRE para el periodo y libro indicados, la normaliza al modelo canónico y la guarda vía upsert. Límite: 10/minuto.

`libro` acepta `ventas` o `compras`. Los dos están implementados y comparten transporte: [sunat/propuesta.py](../../app/services/sunat/propuesta.py) resuelve URL, credenciales y paginación, y delega el mapeo de campos en [sunat/rce.py](../../app/services/sunat/rce.py) o [sunat/rvie.py](../../app/services/sunat/rvie.py) según el libro. Cada uno tiene su endpoint: `URL_SIRE_PROPUESTA` y `URL_SIRE_PROPUESTA_VENTAS`.

Los dos endpoints se comportan igual: exigen `page` y `perPage`, y devuelven `{paginacion: {page, perPage, totalRegistros}, registros: [...], totales: {...}}`. La respuesta se recorre página a página hasta agotar `totalRegistros` o hasta que una página venga incompleta, con `SIRE_MAX_PAGINAS` como freno. Antes se pedía `page=1&perPage=100` fijo y cualquier periodo con más de cien comprobantes se truncaba sin avisar; en ventas eso pasa casi siempre.

`perPage` tiene un techo de **100**: por encima el SIRE responde `422`, así que `descargar` recorta el valor configurado y lo avisa por log.

Respuesta (`StatusResponse`):

```json
{
  "estado": "exito",
  "mensaje": "Se sincronizaron 12 comprobantes",
  "datos": {"nuevos": 8, "actualizados": 4, "descartados": 3}
}
```

`descartados` cuenta comprobantes que llegaron en la respuesta de SUNAT pero no pasaron alguno de los dos filtros: fila inválida (sin serie/número/fecha) o periodo tributario distinto del solicitado.

En la práctica debería ser **cero**: SUNAT devuelve en la propuesta de un periodo justo lo que pertenece a ese periodo. Un `descartados` alto es señal de que algo va mal en el mapeo, no de que SUNAT mande cosas de más.

Errores:

- `502` si la API SIRE responde con un error no controlado, o si no se pudo renovar el token OAuth.
- Si SUNAT responde `422` (sin propuesta para el periodo), **no es un error**: se guarda el periodo como `sin_propuesta` y se devuelve `nuevos: 0`.

## Las boletas ya no se descartan

Hasta ahora la sincronización solo registraba comprobantes cuya serie empezara con `F` o `E`, así que las boletas se perdían en el conteo de `descartados`. El registro de ventas es en su mayoría boletas (`B001`, `EB01`), de modo que el filtro desapareció de los dos libros: ahora se guarda todo lo que SUNAT devuelve.

Dos consecuencias que conviene tener presentes: un periodo de compras puede crecer respecto a lo que había antes, y un periodo de ventas puede pasar de decenas a cientos de comprobantes, todos ellos encolados al análisis con IA. Ver `GEMINI_MIN_INTERVAL_SECONDS` en el [README](../../README.md) antes de lanzar el primer lote grande.

Ver también [flujo de sincronización de la propuesta](../flujo/03-sincronizacion-propuesta.md).
