# Flujo — Sincronización de la propuesta SIRE

[POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta](../endpoints/propuesta.md) llama a [propuesta_service.sincronizar](../../app/services/propuesta_service.py:16).

## Pasos

1. La empresa ya llegó resuelta y verificada por la dependencia [empresa_actual](../../app/api/v1/deps.py:9) — la ruta no vuelve a buscarla.

2. Si `libro` es `ventas`, la ruta responde `501` de inmediato: el libro de ventas (RVIE) no tiene cliente HTTP implementado. Solo `compras` (RCE) continúa.

3. [descargar](../../app/services/sunat/propuesta.py:101) resuelve las credenciales OAuth con [credenciales_cliente](../../app/services/sunat/auth.py:24): usa las propias de la empresa si existen, o cae a las variables de entorno globales.

4. **Manejo del token OAuth**, en [peticion_autenticada](../../app/services/sunat/auth.py:87). Si la empresa no tiene un token guardado, se pide uno nuevo con [obtener_token](../../app/services/sunat/auth.py:32) — una petición tipo `password` contra el servicio de seguridad de SUNAT, usando como username la concatenación directa de RUC y usuario SOL sin separador (formato exigido por SUNAT). Luego se llama a la API SIRE (con la plantilla de `URL_SIRE_PROPUESTA`, reemplazando el placeholder de periodo), pidiendo comprobantes de tipo compras en páginas de 100. Si la respuesta es `401` (token expirado), se llama a [renovar_token](../../app/services/sunat/auth.py:64) y se reintenta la misma petición una vez. Si no hay credenciales de cliente disponibles y el token expiró, se lanza `ErrorSunat` en vez de reintentar sin credenciales.

5. **Mapeo al modelo canónico**, en [a_comprobante](../../app/services/sunat/propuesta.py:64). Cada registro crudo de SUNAT se convierte a un `Comprobante` normalizado (ver [modelo de datos de comprobantes](../modelo-datos/comprobantes.md)). Los nombres de campo se resuelven probando una lista de candidatos por cada destino (serie, número, tipo, montos, etc.) — la respuesta real de SUNAT no está confirmada al 100% contra la documentación oficial, así que el mapeo tolera variaciones de nombre. El JSON crudo completo se conserva en `extra.raw_sire`.

6. **Tres filtros**, aplicados en [propuesta_service.sincronizar](../../app/services/propuesta_service.py:16):
   - `comprobante.es_valido`: descarta filas sin serie, número o fecha de emisión.
   - [serie_aceptada](../../app/services/sunat/propuesta.py:91): solo se aceptan series que empiecen con `F` o `E` (facturas y recibos por honorarios); boletas y otros tipos se descartan.
   - [pertenece_al_periodo](../../app/services/sunat/propuesta.py:95): la fecha de emisión debe caer dentro del periodo solicitado, porque SUNAT a veces devuelve comprobantes de periodos adyacentes en la misma respuesta.

7. **Persistencia**, vía [repo_comprobantes.upsert](../../app/repositories/comprobantes.py:110). El filtro de identidad es `(empresa_id, periodo, libro, origen, tipo_cp, serie, numero)`. Los campos de identidad y el `estado_procesamiento` inicial solo se establecen si el documento es nuevo (`$setOnInsert`); el resto de los campos (contraparte, montos, datos crudos) se actualizan siempre, para que una resincronización refresque los datos sin perder el avance del análisis IA ya hecho.

8. Si SUNAT responde `422`, se interpreta como "sin propuestas para ese periodo" — no es un error: el periodo se marca `sin_propuesta` y se devuelve `nuevos: 0`. Si la sincronización tiene éxito (con o sin comprobantes nuevos), el periodo se marca `sincronizado`.

Ver [modelo de datos de comprobantes](../modelo-datos/comprobantes.md) para el detalle completo de los campos que este proceso escribe, y [flujo de extracción de detalle](04-extraccion-detalle.md) para el paso opcional siguiente.
