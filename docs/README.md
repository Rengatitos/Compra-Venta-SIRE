# Documentación — Sire (facturas-api)

Índice de toda la documentación del sistema.

## Qué es el sistema

API en FastAPI (Python 3.12) que automatiza la gestión contable del Registro de Compras Electrónico de SUNAT vía el sistema SIRE. Permite:

1. Registrar usuarios SOL (credenciales de una empresa o RUC ante SUNAT Operaciones en Línea).
2. Crear periodos fiscales y sincronizar la propuesta de comprobantes de compra desde la API oficial SIRE de SUNAT.
3. Opcionalmente, hacer scraping del detalle de ítems de cada factura directamente del portal de SUNAT, porque la API SIRE no expone ese detalle línea por línea.
4. Clasificar contablemente cada factura con inteligencia artificial, usando como contexto normativa contable general y, opcionalmente, referencias subidas por el propio usuario.
5. Consultar, editar y exportar en Excel o PDF las facturas ya procesadas.
6. Exponer analíticas agregadas para uno o varios RUCs a la vez, pensado para ser consumido por un sistema externo de contabilidad.

El nombre del paquete es facturas-api; el repositorio se llama Sire.

## Stack tecnológico

Framework FastAPI servido con Uvicorn (un solo worker en producción, para ahorrar RAM). Base de datos MongoDB vía el driver asíncrono Motor, en una única base lógica que contiene todas las colecciones de negocio. Autenticación con un JWT propio (no hay OAuth de usuario final; el token identifica una empresa, no una persona). Las contraseñas SOL se cifran de forma reversible, no se hashean, porque se necesitan en texto plano para autenticar contra SUNAT. Límites de tasa en los endpoints más sensibles. Clasificación con inteligencia artificial (Gemini) usando búsqueda de contexto por similitud en memoria, sin una base de datos vectorial dedicada. Scraping con Playwright, limitado únicamente a la extracción de detalle de ítems de facturas ya sincronizadas. Exportación a Excel y PDF.

## Inicio

- [Cómo arrancar](inicio.md) — desarrollo local, Docker, variables de entorno.

## Arquitectura

- [Capas](arquitectura/capas.md) — organización de carpetas, y el flujo routes → services → db.
- [Autenticación](arquitectura/autenticacion.md) — el token propio y las cuatro dependencias de autorización.
- [Cifrado](arquitectura/cifrado.md) — cómo se protegen las contraseñas SOL, e implicaciones de rotar secretos.
- [Rate limiting](arquitectura/rate-limiting.md) — límites de tasa por endpoint.
- [Ciclo de vida](arquitectura/ciclo-de-vida.md) — qué ocurre al arrancar y al apagar el servidor.

## Endpoints

- [SOL Users](endpoints/sol-users.md)
- [Periods](endpoints/periods.md)
- [SIRE](endpoints/sire.md)
- [Analysis](endpoints/analysis.md)
- [Invoices](endpoints/invoices.md)
- [References](endpoints/references.md)
- [Analytics](endpoints/analytics.md)

## Flujo de negocio

Recorrido end-to-end, en orden:

1. [Registro y login](flujo/01-registro-login.md)
2. [Crear periodo](flujo/02-periodos.md)
3. [Sincronización de la propuesta SIRE](flujo/03-sincronizacion-sire.md)
4. [Scraping opcional de detalle de ítems](flujo/04-scraping-detalle.md)
5. [Análisis con IA](flujo/05-analisis-ia.md)
6. [Consulta y exportación de facturas](flujo/06-consulta-exportacion.md)
7. [Analytics](flujo/07-analytics.md)

## Modelo de datos

Todas las colecciones viven en una sola base lógica de MongoDB. No hay un ODM: los documentos se arman a mano como diccionarios en los services y routes, y se validan solo parcialmente vía los schemas de Pydantic.

- [sol_users](modelo-datos/sol-users.md)
- [periodos](modelo-datos/periodos.md)
- [facturas](modelo-datos/facturas.md)
- [vector_global](modelo-datos/vector-global.md)
- [vector_users](modelo-datos/vector-users.md)
- [Índices creados en el arranque](modelo-datos/indices.md)
