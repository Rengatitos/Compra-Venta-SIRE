# Modelo de datos — sol_users

Una empresa o RUC con credenciales SUNAT registradas en el sistema. Poblada por [create_user](../../app/api/routes/sol_users.py:101). No hay un ODM: los documentos se arman a mano como diccionarios en los services y routes, y se validan solo parcialmente vía los schemas de Pydantic de la carpeta schemas.

| Campo | Tipo | Descripción |
|---|---|---|
| id de Mongo | ObjectId | Se usa como identificador de usuario en toda la API, como cadena de texto. |
| ruc | str | RUC de la empresa. |
| usuario | str | Usuario SOL (SUNAT Operaciones en Línea). |
| password | str | Contraseña SOL cifrada (no en texto plano, no hasheada — ver [cifrado](../arquitectura/cifrado.md)). |
| token de SUNAT | str o vacío | Token Bearer OAuth vigente de la API SIRE, cacheado para no pedir uno nuevo en cada request. Se renueva automáticamente ante un error de autorización, o manualmente vía el endpoint de refresh (ver [endpoints — SOL Users](../endpoints/sol-users.md)). |
| credenciales OAuth del cliente SIRE | str o vacío | Se ingresan manualmente (ya no se obtienen por scraping, ver [flujo de registro y login](../flujo/01-registro-login.md)). Si están vacías, el servicio de SIRE cae a las credenciales globales configuradas por variables de entorno (ver [inicio](../inicio.md)). |
| tenant, cliente y cuenta | str o vacío | Identificadores del sistema externo que integra esta API. La sincronización de la propuesta SIRE busca al usuario por esta combinación, no por su id de Mongo (ver [flujo de sincronización SIRE](../flujo/03-sincronizacion-sire.md)). |
| fecha de creación | str, ISO 8601 | Timestamp de creación. |

Índice: sobre el RUC (no único — puede haber múltiples usuarios con el mismo RUC pero distinto usuario SOL; la unicidad real es la combinación de ambos, validada solo a nivel de aplicación al crear el usuario, sin un índice único compuesto que la respalde).
