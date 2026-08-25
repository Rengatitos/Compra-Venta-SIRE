# Autenticación

Todo el código relevante está en [auth.py](../../app/core/auth.py). No hay usuarios "persona": el token identifica un usuario SOL, es decir, una empresa/RUC registrada en el sistema, correspondiente a un documento de la colección sol_users (ver [modelo de datos](../modelo-datos/sol-users.md)).

## Emisión y validación del token

La función [create_token](../../app/core/auth.py:20) firma un payload con el identificador del usuario, el RUC y la fecha de expiración, usando la clave y el algoritmo configurados por variables de entorno (ver [inicio](../inicio.md)). Se emite únicamente al iniciar sesión (ver [endpoints de SOL Users](../endpoints/sol-users.md)).

La función [decode_token](../../app/core/auth.py:29) decodifica el token y valida firma y expiración, devolviendo un error 401 con un mensaje distinto según el token esté expirado o sea inválido.

## Las cuatro dependencias de autorización

**[verify_user](../../app/core/auth.py:48)** es una dependencia de FastAPI que exige el encabezado de autorización con el token, lo decodifica, convierte el identificador de usuario a un identificador de Mongo válido y busca el documento correspondiente en la colección de usuarios SOL. Un detalle importante de diseño: si el usuario fue borrado después de emitirse el token, la petición igual recibe un 401 de "usuario no encontrado" — el token por sí solo nunca basta, siempre se revalida contra la base de datos en cada request.

**[require_same_user](../../app/core/auth.py:73)** es una dependencia compuesta que, además de exigir un token válido, compara el identificador del usuario autenticado contra el identificador que viene en el path de la ruta, devolviendo un error 403 si no coinciden. Es la forma estándar de proteger las rutas anidadas bajo el prefijo de usuario (periodos, facturas, referencias, análisis) para que un usuario autenticado no pueda leer ni modificar datos de otro usuario simplemente cambiando el identificador en la URL. Esta dependencia se creó específicamente para eliminar una comprobación de igualdad de identificadores que estaba duplicada literalmente en varios de los routers antes de extraerse a un solo lugar.

**[verify_admin](../../app/core/auth.py:42)** es una dependencia separada que no se basa en un token JWT sino en un encabezado estático llamado X-Admin-Token, comparado directamente contra la variable de entorno ADMIN_TOKEN. Se usa en los dos endpoints de administración: listar todos los usuarios SOL y el borrado masivo por cuenta SUNAT (ver [endpoints de SOL Users](../endpoints/sol-users.md)).

**verify_dashboard_token**, definida directamente en [analytics.py](../../app/api/routes/analytics.py:15) (no en el módulo de autenticación central), solo decodifica el token sin buscar al usuario en la base ni exigir que sea "el mismo usuario". Los endpoints de analytics confían en que el sistema externo que llama ya validó a qué RUCs tiene acceso, y se los pasa explícitamente como parámetro de consulta. El detalle de esta decisión de diseño está en [endpoints de Analytics](../endpoints/analytics.md).

## Rutas sin protección de identidad explícita

Los endpoints de SIRE ([get_sire_propuesta](../../app/api/routes/sire.py:20) y [post_scrape_detalles](../../app/api/routes/sire.py:93)) usan verify_user (exigen un token válido de algún usuario) pero no require_same_user: la empresa objetivo se determina por tres identificadores propios del sistema externo (tenant, cliente y cuenta), no por el identificador de usuario que aparece en el path. En la práctica, esto significa que cualquier usuario autenticado con un token válido puede disparar una sincronización SIRE para cualquier combinación de esos tres identificadores que exista en la base, siempre que la conozca. Ver más contexto en [flujo de sincronización SIRE](../flujo/03-sincronizacion-sire.md).
