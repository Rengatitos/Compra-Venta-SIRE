# Documentación — Sire

Índice de toda la documentación del sistema.

## Qué es el sistema

API en FastAPI (Python 3.12) con un panel web en React que automatiza la preparación del Registro de Compras (RCE) y del Registro de Ventas (RVIE) de una empresa a partir del SIRE de SUNAT. Permite:

1. Registrar empresas (credenciales de un RUC ante SUNAT Operaciones en Línea) y su plan de cuentas Contasis.
2. Crear periodos fiscales y sincronizar la propuesta de compras y de ventas desde la API oficial SIRE de SUNAT, o importar el ZIP oficial de un ticket del RCE.
3. Extraer del portal SOL, como job asíncrono, el detalle de ítems y el PDF de cada comprobante — la API SIRE no expone ese detalle línea por línea. Las series `E…` se leen del módulo SEE-SOL.
4. Construir la glosa a partir de ese detalle (o de la leyenda del comprobante), permitir su edición manual y asignar a cada comprobante un estado: con glosa, sin glosa, en evaluación o pendiente, según lo que SUNAT publica de cada tipo.
5. Consultar y exportar los comprobantes en el Excel de la plantilla oficial de Contasis (con columnas Observación y Estado glosa), en PDF, en ZIP de respaldos y en el reporte mensual para el contador; conciliar compras contra el resumen oficial del RCE; consultar y descargar los NPD de detracciones.
6. Exponer analíticas agregadas para uno o varios RUCs a la vez.

El repositorio se llama Sire; el paquete Python es `app`. El origen del proyecto era una plataforma de conciliación Contasis ↔ SIRE con un agente de IA para las glosas; la IA se retiró en septiembre de 2026 y la conciliación con Contasis sigue fuera de alcance (ver [PLAN.md](../PLAN.md)).

## Stack tecnológico

FastAPI servido con Uvicorn (un solo worker en producción, para ahorrar RAM). MongoDB vía el driver asíncrono Motor, en una única base lógica. Autenticación con un JWT propio (el token identifica una empresa, no una persona). Las contraseñas SOL se cifran de forma reversible con Fernet, no se hashean, porque se necesitan en texto plano para autenticar contra SUNAT. Límites de tasa con `slowapi` en los endpoints más sensibles. Scraping con Playwright, ejecutado como job asíncrono y encolado por empresa. Exportación a Excel y PDF con `openpyxl` y `reportlab`. Frontend en React 19 + Vite (ver [frontend/README.md](../frontend/README.md)).

## Inicio

- [Cómo arrancar](inicio.md) — desarrollo local, tests, Docker, variables de entorno, scripts.

## Arquitectura

- [Capas](arquitectura/capas.md) — organización de carpetas, el flujo routes → services/repositories → db, y la convención de rutas.
- [Autenticación](arquitectura/autenticacion.md) — el JWT propio y las dependencias de autorización.
- [Cifrado](arquitectura/cifrado.md) — cómo se protegen las contraseñas SOL, e implicaciones de rotar secretos.
- [Rate limiting](arquitectura/rate-limiting.md) — límites de tasa por endpoint.
- [Ciclo de vida](arquitectura/ciclo-de-vida.md) — qué ocurre al arrancar y al apagar el servidor, y la recarga en desarrollo.

## Endpoints

- [Auth y Empresas](endpoints/empresas.md)
- [Periodos](endpoints/periodos.md)
- [Maestro de cuentas](endpoints/plan-cuentas.md)
- [Propuesta SIRE](endpoints/propuesta.md) — sincronización por API e importación del ZIP oficial
- [Comprobantes](endpoints/comprobantes.md) — listado, incompletos, anulados, cobertura, exportación, conciliación RCE
- [Detalle SUNAT (asíncrono)](endpoints/detalle.md)
- [PDFs de comprobantes (asíncrono)](endpoints/pdfs.md) — descarga por libro, ZIP con manifiesto y ZIP completo
- [Detracciones (NPD)](endpoints/detracciones.md)
- [Auditoría](endpoints/auditoria.md)
- [Reporte y comprobantes asociados](endpoints/reporte-asociado.md)
- [Jobs](endpoints/jobs.md)
- [Analytics](endpoints/analytics.md)
- [Apaclla Bot](endpoints/apaclla-bot.md) — vinculación del bot y comprobantes externos

## Flujo de negocio

Recorrido end-to-end, en orden:

1. [Registro y login](flujo/01-registro-login.md)
2. [Crear periodo](flujo/02-periodos.md)
3. [Sincronización de la propuesta SIRE](flujo/03-sincronizacion-propuesta.md)
4. [Extracción de detalle (scraping, asíncrono)](flujo/04-extraccion-detalle.md)
5. [Glosa y estado por tipo de comprobante](flujo/05-glosa-y-estado.md)
6. [Consulta y exportación de comprobantes](flujo/06-consulta-exportacion.md)
7. [Detracciones (NPD)](flujo/07-detracciones.md)
8. [Analytics](flujo/08-analytics.md)

## Modelo de datos

Todas las colecciones viven en una sola base lógica de MongoDB. No hay un ODM: los documentos se arman en la capa de repositorios ([app/repositories](../app/repositories)), a partir del modelo de dominio Pydantic ([app/domain/comprobante.py](../app/domain/comprobante.py)).

- [empresas](modelo-datos/empresas.md)
- [periodos](modelo-datos/periodos.md)
- [comprobantes](modelo-datos/comprobantes.md)
- [jobs](modelo-datos/jobs.md)
- [comprobantes externos y códigos de vinculación](modelo-datos/comprobantes-externos.md)
- [Índices creados en el arranque](modelo-datos/indices.md)

## Fuera de alcance hoy

- **Aceptar / reemplazar la propuesta del SIRE.** El cliente hacia SUNAT hoy solo lee (descarga la propuesta por API o por ticket).
- **Conciliación contra Contasis.** Contasis entra sólo como plan de cuentas y sale como plantilla Excel; no hay parser de sus registros ni motor de conciliación.
- **Campos de auditoría refinados.** El cliente no los ha especificado.
- **Recibos por honorarios (tipo 02).** SUNAT los publica por otro módulo de SOL que el scraper no recorre; ver [glosa y estado](flujo/05-glosa-y-estado.md).

## Convención de esta documentación

Los enlaces al código apuntan al archivo y nombran la función o constante; no llevan número de línea, porque esos anclajes se desfasan con cada cambio.
