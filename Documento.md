# Arquitectura y Flujo del Sistema: Automatización SIRE - SUNAT

## 1. Visión General y Estrategia

El sistema automatiza la validación, aceptación y auditoría de los registros de compras y ventas electrónicos mediante el SIRE (SUNAT).

Para mantener la simplicidad y robustez, el sistema se divide en dos fases operativas:

- **Fase 1 (Operativa/Cumplimiento):** Conciliación automática entre el sistema contable interno (**Contasis**) y la propuesta del **SIRE (SUNAT)**. Si cuadran, se acepta; si difieren, se reemplaza la propuesta usando los datos de Contasis.

- **Fase 2 (Auditoría/IA):** Proceso en segundo plano (Scraping) para descargar PDFs detallados, estructurar los datos y ejecutar un Agente de IA que genere glosas y reportes para el auditor.

> **Nota sobre la "API del SIRE":** SUNAT cuenta con una API oficial para el SIRE (mediante credenciales de API SUNAT) que permite descargar propuestas en `.zip` y subir reemplazos. Se debe priorizar el uso de esta API oficial para la **Fase 1**. El scraping (Playwright) debe reservarse **solo para la Fase 2** (descarga masiva de PDFs visuales), ya que la SUNAT suele bloquear scrapers que operan de forma agresiva.

## 2. Stack Tecnológico

- **Backend:** FastAPI (Python) - Ideal para tareas asíncronas y scripts de scraping/IA.
- **Base de Datos:** MongoDB Atlas (NoSQL) - Flexible para guardar JSONs de facturas y configuraciones.
- **Frontend:** React (TypeScript) desplegado en Vercel.
- **Infraestructura Backend:** Render.
- **IA:** Agente de IA (API gemini free) para análisis de auditoría.

## 3. Flujo Lógico del Backend

### Pre-requisitos (Configuración Inicial)

1. **Información de Empresa:** Registrar credenciales SOL, RUC y contexto del negocio (a qué se dedica).
2. **Carga del Maestro de Cuentas:** Endpoint para subir el Excel (Tipo, análisis, centro de costos, descripción). Esto se parsea y se guarda en MongoDB.

### Fase 1: Flujo de Ventas y Compras (Conciliación)

_Reutilizable para Ventas (RVIE) y Compras (RCE)_

1. **Obtención de Propuesta (SUNAT):** El backend se conecta a la API SIRE, envía AÑO y MES, y descarga el ticket con la "Propuesta".

2. **Obtención de Datos Internos (Contasis):** Se recibe o extrae la data de Contasis del mismo periodo.

3. **Motor de Conciliación:**
    - Se comparan totales y comprobantes (Contasis vs Propuesta SUNAT).
    - **Caso A (Match 100%):** Se envía petición a SUNAT para "Aceptar Propuesta" $\rightarrow$ Obtiene Check de Aprobación.
    - **Caso B (Diferencias):** El backend genera un archivo ZIP preliminar basado en Contasis, llama al endpoint de SUNAT de "Reemplazo de Propuesta", valida estructura y solicita Check de Aprobación.
4. **Generación de Registro:** Al tener los checks de Ventas y Compras, se envía la confirmación final al SIRE.

### Fase 2: Flujo de Auditoría e IA (Asíncrono)

1. **Scraping Automatizado:** Dado un AÑO y MES, un bot (Playwright integrado en Python) entra al portal SOL de SUNAT.

    - Calcula automáticamente `fecha_inicio` (01/MM/AAAA) y `fecha_fin` (31/MM/AAAA).
    - Itera sobre Facturas y Boletas (y sus Notas de Crédito/Débito) aceptadas en la Fase 1.
    - Descarga los PDFs.
2. **Almacenamiento Local/Cloud:** Los PDFs se guardan con la siguiente estructura y luego se zipean:
    - `data/ventas/{AÑO}/{MES}/facturas/` (y boletas)
    - `data/compras/{AÑO}/{MES}/facturas/` (y boletas)
3. **Agente de IA:**
    - Extrae el texto de los PDFs.
    - Cruza la info del PDF + Contexto de la Empresa + Maestro de Cuentas (Excel).
    - Genera los "Campos de Auditoría" (glosa detallada, para qué se usó, por qué).
4. **Exportación:** Se genera la tabla comparativa y el ZIP de respaldos para el Auditor.

## 4. Diseño de la API (Contrato para el Frontend)

Estos son los endpoints que debes construir en FastAPI para que el Frontend de React pueda interactuar con el sistema:
### Módulo 1: Configuración

- `POST /api/v1/config/empresa`
    - **Payload:** RUC, Clave SOL, descripción del negocio.
    - **Acción:** Guarda credenciales de la empresa en Mongo.
- `POST /api/v1/config/cuentas/upload`
    - **Payload:** Archivo `.xlsx` (Maestro de cuentas).
    - **Acción:** Procesa el Excel y actualiza la colección de mapeo de cuentas.

### Módulo 2: Operaciones SIRE (Fase 1)

- `POST /api/v1/sire/conciliar`
    - **Payload:** `{ "periodo": "2026-08", "tipo": "VENTAS" | "COMPRAS", "datos_contasis": [...] }`
    - **Acción:** Descarga propuesta SUNAT, compara con Contasis. Devuelve el resultado de la conciliación (Match o Diferencias).
- `POST /api/v1/sire/aprobar`
    - **Payload:** `{ "periodo": "2026-08", "tipo": "VENTAS" | "COMPRAS", "accion": "ACEPTAR" | "REEMPLAZAR" }`
- `POST /api/v1/sire/generar-registro`
    - **Payload:** `{ "periodo": "2026-08" }`
    - **Acción:** Verifica que Ventas y Compras tengan check y genera el registro final.

### Módulo 3: Auditoría y Scraping (Fase 2)

- `POST /api/v1/audit/iniciar-extraccion`
    - **Payload:** `{ "periodo": "2026-08", "tipo": "VENTAS" | "COMPRAS" }`
    - **Acción:** Dispara una tarea en segundo plano (BackgroundTasks de FastAPI o Celery) que enciende el scraper para descargar los PDFs. Devuelve un `task_id`. 
- `GET /api/v1/audit/estado-extraccion/{task_id}`
    - **Acción:** Para que el frontend muestre una barra de progreso de las descargas.
- `POST /api/v1/audit/ejecutar-ia`
    - **Payload:** `{ "periodo": "2026-08" }`
    - **Acción:** Inicia el análisis del Agente de IA sobre los datos extraídos.
- `GET /api/v1/audit/reporte/{periodo}`
    - **Acción:** Devuelve el JSON con la tabla comparativa, las glosas detalladas y la URL para descargar el archivo ZIP (`data/ventas.../archivos.zip`).

## Próximos pasos sugeridos para el Desarrollo

1. **Investigación API SIRE:** Antes de programar, lee la documentación oficial de SUNAT para desarrolladores sobre los endpoints del SIRE (descarga de propuestas en `.zip`).
2. revisar los documentos agregados en data