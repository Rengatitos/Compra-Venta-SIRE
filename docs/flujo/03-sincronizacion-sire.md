# Flujo — Sincronización de la propuesta SIRE

El endpoint [get_sire_propuesta](../endpoints/sire.md) llama a [obtener_propuesta](../../app/services/sire_service.py:145).

## Pasos

1. Busca al usuario SOL por la combinación de tenant, cliente y cuenta en la colección de usuarios SOL — no por el identificador de usuario del path (ver la nota de autorización en [endpoints — SIRE](../endpoints/sire.md)).

2. Resuelve las credenciales OAuth con [_obtener_credenciales_sunat](../../app/services/sire_service.py:125): usa las credenciales propias del usuario si existen; si no, cae a las variables de entorno globales de credenciales SUNAT (un fallback compartido, útil cuando varios tenants usan el mismo cliente SIRE registrado).

3. **Manejo del token OAuth.** Si el usuario no tiene un token guardado, se pide uno nuevo con [obtener_token_api_oficial](../../app/services/sire_service.py:15) — una petición de tipo contraseña contra el servicio de seguridad de SUNAT, usando como nombre de usuario la concatenación directa del RUC y el usuario SOL sin separador (formato exigido por SUNAT), y solicitando el alcance correspondiente a la API SIRE. Luego se llama a la API SIRE (con la plantilla de URL configurada, reemplazando el placeholder de periodo) pidiendo comprobantes de tipo compras, en páginas de 100. Si la API SIRE devuelve un error de autorización (token expirado), se llama a [_renovar_token](../../app/services/sire_service.py:131) para pedir un token nuevo y se reintenta la misma petición una vez. Esta función de renovación es un helper compartido entre la obtención inicial del token y este reintento — antes, el bloque de "descifrar la contraseña, pedir el token y guardarlo" estaba duplicado en ambos puntos del código, antes de extraerse a un solo lugar. Si no hay credenciales de cliente disponibles y el token expiró, se lanza una excepción explícita en vez de reintentar sin credenciales.

4. **Procesamiento de comprobantes**, en [procesar_y_guardar_comprobantes](../../app/services/sire_service.py:46). Por cada registro devuelto por SUNAT:
   - Solo se procesan comprobantes cuya serie empiece con F o E (facturas y recibos por honorarios o similares); se descartan boletas y otros tipos de comprobante.
   - El RUC del emisor se toma del campo correspondiente al proveedor, con una segunda opción como respaldo si ese campo viene vacío o en cero.
   - El nombre del proveedor se resuelve probando varios campos del payload de SUNAT en un orden de prioridad específico, priorizando explícitamente los campos etiquetados como "proveedor" para evitar tomar por error la razón social del comprador, que también viene presente en la respuesta de SUNAT.
   - Se valida que la fecha de emisión del comprobante caiga dentro del periodo solicitado; si no, el registro se descarta, porque SUNAT a veces devuelve comprobantes de periodos adyacentes en la misma respuesta.
   - Se hace una actualización con upsert sobre la colección de facturas: los campos "de identidad" solo se establecen si el documento es nuevo (no se pisan en una resincronización), mientras que los campos que sí deben refrescarse en cada sincronización (RUC del emisor, nombre del proveedor, montos, datos crudos de SUNAT) se actualizan siempre. El filtro de ese upsert es la combinación de usuario, periodo y número de serie.

5. Si la API SIRE responde con un código 422, se interpreta como "sin propuestas para ese periodo" — no es un error: el periodo se marca como terminado y se retorna una lista vacía. Si responde con éxito, el periodo también se marca como terminado, una vez guardados los comprobantes.

Ver [modelo de datos de facturas](../modelo-datos/facturas.md) para el detalle completo de los campos que este proceso escribe, y [flujo de scraping de detalle](04-scraping-detalle.md) para el paso opcional siguiente.
