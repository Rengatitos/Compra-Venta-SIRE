# Documentación — Sire

Índice de toda la documentación del sistema.

## Qué es el sistema

API en FastAPI (Python 3.12) que automatiza la gestión contable del Registro de Compras Electrónico de SUNAT vía el sistema SIRE. Permite:

1. Registrar empresas (credenciales de un RUC ante SUNAT Operaciones en Línea).
2. Crear periodos fiscales y sincronizar la propuesta de comprobantes de compra desde la API oficial SIRE de SUNAT.
3. Opcionalmente, hacer scraping del detalle de ítems de cada comprobante directamente del portal de SUNAT, como un job asíncrono — la API SIRE no expone ese detalle línea por línea.
4. Clasificar contablemente cada comprobante con inteligencia artificial, usando como contexto normativa contable general y, opcionalmente, referencias subidas por la propia empresa.
5. Consultar, editar y exportar en Excel o PDF los comprobantes ya procesados.
6. Exponer analíticas agregadas para uno o varios RUCs a la vez, pensado para ser consumido por un sistema externo de contabilidad.

El repositorio se llama Sire; el paquete Python es `app`.

## Stack tecnológico

FastAPI servido con Uvicorn (un solo worker en producción, para ahorrar RAM). MongoDB vía el driver asíncrono Motor, en una única base lógica. Autenticación con un JWT propio (el token identifica una empresa, no una persona). Las contraseñas SOL se cifran de forma reversible con Fernet, no se hashean, porque se necesitan en texto plano para autenticar contra SUNAT. Límites de tasa con `slowapi` en los endpoints más sensibles. Clasificación con Gemini usando búsqueda de contexto por similitud en memoria, sin una base de datos vectorial dedicada. Scraping con Playwright, limitado a la extracción de detalle de ítems de comprobantes ya sincronizados, ejecutado como job asíncrono. Exportación a Excel y PDF con `openpyxl` y `reportlab`.

## Inicio

- [Cómo arrancar](inicio.md) — desarrollo local, tests, Docker, variables de entorno.

## Arquitectura

- [Capas](arquitectura/capas.md) — organización de carpetas, el flujo routes → services/repositories → db, y la convención de rutas.
- [Autenticación](arquitectura/autenticacion.md) — el JWT propio y las dependencias de autorización.
- [Cifrado](arquitectura/cifrado.md) — cómo se protegen las contraseñas SOL, e implicaciones de rotar secretos.
- [Rate limiting](arquitectura/rate-limiting.md) — límites de tasa por endpoint.
- [Ciclo de vida](arquitectura/ciclo-de-vida.md) — qué ocurre al arrancar y al apagar el servidor.

## Endpoints

- [Auth y Empresas](endpoints/empresas.md)
- [Periodos](endpoints/periodos.md)
- [Maestro de cuentas](endpoints/plan-cuentas.md)
- [Propuesta SIRE](endpoints/propuesta.md)
- [Comprobantes](endpoints/comprobantes.md)
- [Análisis IA](endpoints/analisis.md)
- [Detalle SUNAT (asíncrono)](endpoints/detalle.md)
- [PDFs de comprobantes (asíncrono)](endpoints/pdfs.md)
- [Auditoría](endpoints/auditoria.md)
- [Jobs](endpoints/jobs.md)
- [Referencias](endpoints/referencias.md)
- [Analytics](endpoints/analytics.md)

## Flujo de negocio

Recorrido end-to-end, en orden:

1. [Registro y login](flujo/01-registro-login.md)
2. [Crear periodo](flujo/02-periodos.md)
3. [Sincronización de la propuesta SIRE](flujo/03-sincronizacion-propuesta.md)
4. [Extracción de detalle (scraping, asíncrono)](flujo/04-extraccion-detalle.md)
5. [Análisis con IA](flujo/05-analisis-ia.md)
6. [Consulta y exportación de comprobantes](flujo/06-consulta-exportacion.md)
7. [Analytics](flujo/07-analytics.md)

## Modelo de datos

Todas las colecciones viven en una sola base lógica de MongoDB. No hay un ODM: los documentos se arman en la capa de repositorios ([app/repositories](../app/repositories)), a partir del modelo de dominio Pydantic ([app/domain/comprobante.py](../app/domain/comprobante.py)).

- [empresas](modelo-datos/empresas.md)
- [periodos](modelo-datos/periodos.md)
- [comprobantes](modelo-datos/comprobantes.md)
- [jobs](modelo-datos/jobs.md)
- [vector_global](modelo-datos/vector-global.md)
- [vector_usuarios](modelo-datos/vector-usuarios.md)
- [Índices creados en el arranque](modelo-datos/indices.md)

## Fuera de alcance hoy

- **Aceptar / reemplazar la propuesta del SIRE.** El cliente hacia SUNAT hoy solo lee (descarga la propuesta).
- **Conciliación contra Contasis** y **plan de cuentas**. Ver [PLAN.md](../PLAN.md) para el diseño de esta fase.
