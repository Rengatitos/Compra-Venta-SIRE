# Capas y organización del código

## Estructura general

El código de la aplicación vive bajo la carpeta `app`. En su raíz está [main.py](../../app/main.py), que instancia FastAPI, define el lifespan, monta el router versionado, configura CORS y registra el limitador de tasa.

Dentro de esa carpeta hay seis subcarpetas:

- **`api/v1`** contiene las rutas de la API versionada. [deps.py](../../app/api/v1/deps.py) define las dependencias compartidas (`empresa_actual`, `empresa_id`, `periodo_valido`, `libro_valido`); [router.py](../../app/api/v1/router.py) monta cada router con su prefijo, en un único lugar. La carpeta `routes/` tiene un archivo por grupo de endpoints: `auth.py` (login), `empresas.py` (CRUD y token SUNAT), `periodos.py` (CRUD de periodos), `propuesta.py` (sincronización con el SIRE), `comprobantes.py` (consulta, edición y exportación), `analisis.py` (disparo del análisis con IA), `detalle.py` (extracción de detalle vía scraping, como job), `jobs.py` (consulta de jobs), `referencias.py` (PDFs de referencia para RAG) y `analytics.py` (endpoints agregados para un dashboard externo).
- **`domain`** contiene lógica pura, sin I/O: el modelo canónico de comprobante y sus normalizadores ([comprobante.py](../../app/domain/comprobante.py)), los catálogos de códigos SUNAT ([catalogos.py](../../app/domain/catalogos.py)), la validación del formato de periodo ([periodo.py](../../app/domain/periodo.py)), el contrato de trabajos asíncronos ([jobs.py](../../app/domain/jobs.py)) y la deducción del rubro desde el CIIU ([rubro.py](../../app/domain/rubro.py)). Ningún módulo de esta carpeta importa `app.db`, `app.repositories` ni `requests`: todo lo que entra son estructuras de datos, y por eso es la única carpeta cubierta por tests que no requieren Mongo ni SUNAT (ver [tests/domain](../../tests/domain)).
- **`repositories`** es el único punto de acceso a MongoDB. Un archivo por colección: `empresas.py`, `periodos.py`, `comprobantes.py`, `jobs.py`, `vectores.py` (que cubre `vector_global` y `vector_usuarios`). [_mongo.py](../../app/repositories/_mongo.py) centraliza los nombres de colección y las conversiones entre el dominio y BSON — en particular, `Decimal` ↔ `Decimal128` para los montos y `date` ↔ `datetime` para las fechas.
- **`core`** contiene la configuración y los mecanismos transversales: [config.py](../../app/core/config.py) (variables de entorno), [auth.py](../../app/core/auth.py) (JWT y dependencias de autorización, ver [autenticación](autenticacion.md)) y [encryption.py](../../app/core/encryption.py) (cifrado de contraseñas SOL, ver [cifrado](cifrado.md)).
- **`db`** tiene un único archivo, [database.py](../../app/db/database.py), con la conexión a Mongo vía Motor y un único accesor de base — [get_db](../../app/db/database.py:31).
- **`schemas`** reúne los modelos Pydantic de request/response: `empresa.py`, `periodo.py`, `comprobante.py`, `job.py` y `generic.py` (respuestas genéricas reutilizadas entre rutas).
- **`services`** contiene la lógica de negocio: `propuesta_service.py` (orquesta la sincronización con el SIRE), `comprobante_service.py` (serialización hacia la API y armado del texto para la IA), `jobs_service.py` (ejecución de trabajos asíncronos con seguimiento de progreso), `detalle_service.py` (extracción de detalle vía scraping, como job), `analisis_ia.py` (integración con Gemini y RAG), `analytics_service.py` (agregaciones para el dashboard), `export_service.py` (PDF de revisión y Excel de un comprobante), `plantilla_excel.py` (el registro de compras/ventas sobre la plantilla oficial de Contasis), `scraping_sunat.py` (automatización del portal SOL con Playwright) y el paquete `sunat/` (cliente HTTP hacia la API oficial: `auth.py` para OAuth, `propuesta.py` para la descarga —URL, credenciales y paginación— y `rce.py` / `rvie.py` para el mapeo de campos de cada libro, sobre los helpers comunes de `campos.py`).

Todos los archivos de inicialización de paquete están vacíos; solo marcan paquetes de Python.

## El flujo de una request: routes → services/repositories → db

Toda request HTTP atraviesa las mismas capas, en el mismo orden:

**routes.** Cada archivo de `api/v1/routes/` define un router de FastAPI, valida el cuerpo de la petición con los schemas de Pydantic, resuelve las dependencias de autorización (`empresa_actual`, `empresa_id`, o `verify_admin` para los pocos endpoints administrativos) y delega la lógica de negocio a la capa de servicios. Los routers tampoco declaran su propio prefijo de path — se define al montar cada router en [router.py](../../app/api/v1/router.py), incluyendo los parámetros de ruta (`{ruc}`, `{periodo}`, `{libro}`).

**services.** Contienen la lógica de negocio: llamadas a la API oficial de SUNAT, llamadas a Gemini, generación de reportes, agregaciones y ejecución de jobs. Reciben la conexión de base de datos como parámetro explícito.

**repositories.** Son la única capa que arma queries de Mongo y sabe el nombre de cada colección. Los services no acceden a `db["comprobantes"]` directamente — llaman a `repo_comprobantes.listar(db, ...)`. Esta capa también es responsable de convertir entre el modelo de dominio (`Decimal`, `date`) y su representación en BSON (`Decimal128`, `datetime`).

**db.** [database.py](../../app/db/database.py) es la capa mínima de conexión a Mongo vía Motor. Expone [get_db](../../app/db/database.py:31), que lee la variable global inicializada por [connect_to_mongo](../../app/db/database.py:16) durante el arranque de la aplicación. Todas las colecciones del sistema viven en una única base lógica, cuyo nombre se define en `MONGO_FACTURASDB_NAME`.

## Convención de rutas

```
/api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/<recurso>
```

La identidad del recurso es el **RUC**, no el `_id` de Mongo. El sujeto de la request sale siempre del **JWT**, nunca del path: la dependencia [empresa_actual](../../app/api/v1/deps.py:9) resuelve la empresa desde el token y verifica que su RUC coincida con el del path, devolviendo `403` si no.

`libro` (`ventas` \| `compras`) es un path param, no dos árboles de rutas separados: ventas y compras comparten el grueso de la lógica y duplicar rutas garantizaría que divergieran. Lo llevan `propuesta`, `analisis` y `detalle`.

## Otros temas de arquitectura

- [Autenticación](autenticacion.md) — JWT propio y las dependencias de autorización.
- [Cifrado](cifrado.md) — cómo se protegen las contraseñas SOL.
- [Rate limiting](rate-limiting.md) — límites de tasa por endpoint.
- [Ciclo de vida de la aplicación](ciclo-de-vida.md) — qué ocurre al arrancar y al apagar el servidor.

Además, [main.py](../../app/main.py:71) configura CORS con la lista de orígenes de `CORS_ORIGINS`, credenciales permitidas, y todos los métodos y encabezados habilitados.
