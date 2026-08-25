# Capas y organización del código

## Estructura general

El código de la aplicación vive bajo la carpeta app. En su raíz está [main.py](../../app/main.py), que instancia FastAPI, define el lifespan, monta los routers, configura CORS y registra el limitador de tasa.

Dentro de esa carpeta hay cinco subcarpetas:

- La carpeta de rutas de la API contiene un archivo por grupo de endpoints: [sol_users.py](../../app/api/routes/sol_users.py) (CRUD de usuarios SOL, login, refresh de token, limpieza), [periods.py](../../app/api/routes/periods.py) (CRUD de periodos fiscales), [sire.py](../../app/api/routes/sire.py) (sincronización de la propuesta SIRE y disparo del scraping de detalle en segundo plano), [analysis.py](../../app/api/routes/analysis.py) (disparo del análisis contable con IA), [invoices.py](../../app/api/routes/invoices.py) (consulta, edición y exportación de facturas), [references.py](../../app/api/routes/references.py) (subida, listado y borrado de PDFs de referencia para RAG por usuario) y [analytics.py](../../app/api/routes/analytics.py) (endpoints agregados para un dashboard externo).
- La carpeta core contiene la configuración y los mecanismos transversales: [config.py](../../app/core/config.py) (variables de entorno, ver [inicio](../inicio.md)), [auth.py](../../app/core/auth.py) (JWT y dependencias de autorización, ver [autenticación](autenticacion.md)) y [encryption.py](../../app/core/encryption.py) (cifrado de contraseñas SOL, ver [cifrado](cifrado.md)).
- La carpeta db tiene un único archivo, [database.py](../../app/db/database.py), con la conexión a Mongo vía Motor y los accesores de colecciones.
- La carpeta schemas reúne los modelos Pydantic de request/response, separados por dominio: usuarios, periodos, facturas y esquemas genéricos.
- La carpeta services contiene la lógica de negocio: integración con SUNAT (SIRE y scraping), análisis con IA, persistencia de embeddings, serialización y exportación de facturas, agregaciones para analytics y mantenimiento de datos. Cada uno de estos servicios se documenta con detalle en las páginas de [flujo de negocio](../flujo/01-registro-login.md) y [modelo de datos](../modelo-datos/facturas.md).

Todos los archivos de inicialización de paquete del proyecto están vacíos; solo marcan paquetes de Python.

## El flujo de una request: routes → services → db

Toda request HTTP atraviesa siempre las mismas tres capas, en el mismo orden:

**routes.** Cada archivo de la carpeta de rutas define un router de FastAPI, valida el cuerpo de la petición con los schemas de Pydantic, resuelve las dependencias de autorización (verificación de usuario, de identidad del mismo usuario, o de administrador — ver [autenticación](autenticacion.md)) y delega la lógica de negocio a la capa de servicios. Un detalle importante: los routers no declaran su propio prefijo de path. Los prefijos —incluyendo parámetros de ruta como el identificador de usuario o el periodo— se definen al montar cada router en [main.py](../../app/main.py:111). Esto significa que, por ejemplo, el router de SIRE no "sabe" cuál es su propio path completo; depende enteramente de cómo se lo incluyó al armar la aplicación. El detalle de cada endpoint está en la sección de [endpoints](../endpoints/sol-users.md).

**services.** Los archivos de la carpeta de servicios contienen la lógica de negocio: llamadas a las APIs externas de SUNAT, llamadas a Gemini, generación de reportes y agregaciones. Reciben la conexión de base de datos (la base de negocio, la base de usuarios, o una colección específica) como parámetro explícito — no importan la conexión global directamente, salvo casos puntuales de import diferido dentro del propio módulo de análisis IA.

**db.** [database.py](../../app/db/database.py) es la capa mínima de acceso a Mongo vía Motor. Expone cuatro funciones de acceso a nivel de módulo — [get_db](../../app/db/database.py:42), [get_user_db](../../app/db/database.py:47), [get_vector_global_col](../../app/db/database.py:52) y [get_vector_users_col](../../app/db/database.py:57)— que leen variables globales inicializadas por [connect_to_mongo](../../app/db/database.py:20) durante el arranque de la aplicación. Un detalle no obvio: get_db y get_user_db devuelven el mismo objeto de base de datos (la base de usuarios y la base de negocio son, en la práctica, la misma base lógica). Son accesores separados a propósito, para dejar clara la intención semántica de cada ruta ("esta necesita datos de negocio" frente a "esta necesita el usuario"), no porque existan dos bases de datos distintas. Todas las colecciones del sistema — usuarios SOL, periodos, facturas, y las dos colecciones de embeddings— viven en la misma base lógica, cuyo nombre se define en la variable de entorno MONGO_FACTURASDB_NAME.

## Otros temas de arquitectura

- [Autenticación](autenticacion.md) — JWT propio y las cuatro dependencias de autorización.
- [Cifrado](cifrado.md) — cómo se protegen las contraseñas SOL.
- [Rate limiting](rate-limiting.md) — límites de tasa por endpoint.
- [Ciclo de vida de la aplicación](ciclo-de-vida.md) — qué ocurre al arrancar y al apagar el servidor.

Además, [main.py](../../app/main.py:103) configura CORS de forma abierta: cualquier origen, credenciales permitidas, y todos los métodos y encabezados habilitados.
