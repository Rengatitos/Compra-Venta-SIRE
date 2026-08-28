# Plan de desarrollo — Automatización SIRE/SUNAT

**Backend, 2 personas.** Persona A: backend. Persona B: backend (y frontend en una fase posterior).

---

## 1. Por qué este plan

`Documento.md` describe el sistema objetivo: conciliar automáticamente el sistema contable interno (**Contasis**) contra la **propuesta del SIRE (SUNAT)**, aceptar o reemplazar esa propuesta, y luego correr un proceso asíncrono de auditoría con IA.

El repo **ya tiene un backend funcionando**, pero cubre aproximadamente el 40% de esa visión y está construido sobre supuestos que hoy limitan el crecimiento. Este documento sirve para dos cosas: que ambas personas entiendan la aplicación completa antes de tocar código, y que puedan trabajar en paralelo sin pisarse.

### Lo que ya existe y funciona (reutilizar, no reescribir)

| Pieza | Ubicación | Estado |
|---|---|---|
| OAuth SUNAT (token password grant, RUC+usuario concatenado) | [sire_service.py:15](app/services/sire_service.py:15) | Funciona. Es la pieza más valiosa del repo. |
| Renovación de token + retry en 401 | [sire_service.py:131](app/services/sire_service.py:131) | Funciona. Patrón a generalizar. |
| Descarga de propuesta RCE (compras) vía endpoint `/busqueda` | [sire_service.py:145](app/services/sire_service.py:145) | Funciona, pero es JSON paginado — no el flujo por ticket. |
| Cifrado de clave SOL | [encryption.py](app/core/encryption.py) | Funciona. |
| JWT + dependencias de autorización | [auth.py](app/core/auth.py) | Funciona. |
| Scraping portal SOL con Playwright (login + detalle de ítems) | [scraping_sunat.py:14](app/services/scraping_sunat.py:14) | El `_hacer_login` es reutilizable tal cual. |
| Análisis IA Gemini + RAG (chunking PDF, embeddings, búsqueda de contexto) | [analisis_ia.py:36](app/services/analisis_ia.py:36), [:111](app/services/analisis_ia.py:111), [:170](app/services/analisis_ia.py:170) | Funciona. |
| Exportación Excel/PDF de facturas | [export_service.py:58](app/services/export_service.py:58) | Base para el reporte de auditoría. |
| CRUD periodos, facturas, usuarios SOL, analytics | `app/api/routes/` | Funciona. |
| Validación de periodo `YYYYMM` | [period.py:5](app/schemas/period.py:5) | Reutilizar en todo el proyecto. |

### Lo que falta (el trabajo de este plan)

1. **Ventas (RVIE) no existe.** Todo el código asume compras: `tipo_operacion` está hardcodeado a `"compras"` ([facturas.md](docs/modelo-datos/facturas.md)), y `procesar_y_guardar_comprobantes` descarta cualquier serie que no empiece con `F` o `E` ([sire_service.py:60](app/services/sire_service.py:60)) — o sea, descarta boletas, que son el volumen principal de ventas en los casos reales de `source/`.
2. **Contasis no entra al sistema.** No hay parser del Excel ni modelo para sus registros.
3. **No hay motor de conciliación.** Es el corazón del producto y no existe.
4. **No hay aceptar / reemplazar propuesta ni generar registro.** El cliente SIRE actual solo lee.
5. **No hay flujo por ticket.** SUNAT responde a las operaciones de escritura con un ticket asíncrono; el código actual no lo modela.
6. **No hay seguimiento de jobs.** `BackgroundTasks` se dispara y se olvida ([sire.py:106](app/api/routes/sire.py:106)): el frontend no puede mostrar progreso.
7. **No hay maestro de cuentas.** `source/CUENTAS CONTABLES.xlsx` (2.883 filas de PCGE con tipo, análisis y centro de costos) no se carga a ningún lado, aunque la IA lo necesita para clasificar.
8. **No se descargan PDFs ni se genera el ZIP para el auditor.**

### Deuda a corregir en el camino

- **La ruta SIRE ignora su propio `user_id`.** `GET /sol-users/{user_id}/periodos/{periodo}/propuesta` resuelve la empresa por `tenant_id`+`cliente_id`+`cuenta_id` que llegan como *query params* ([sire.py:20](app/api/routes/sire.py:20), [sire_service.py:154](app/services/sire_service.py:154)), no por el `user_id` del path ni por el JWT. Es una inconsistencia de autorización, ya señalada en `docs/endpoints/sire.md`.
- **`get_db()` y `get_user_db()` devuelven la misma base**, mantenidos como accesores separados solo por intención semántica ([capas.md](docs/arquitectura/capas.md)).
- **CORS abierto a `*` con credenciales** ([main.py:103](app/main.py:103)).
- **Los servicios acceden a Mongo inline** (`db["facturas"]`), sin capa de repositorio: la lógica de negocio no es testeable sin base de datos.
- **`GEMINI_API_KEY` se lee del entorno directo**, fuera de `Settings` — no se valida al arrancar.

---

## 2. Decisión de arquitectura: convención de API

Se evaluó qué convención cumple mejores prácticas. **Ninguna de las dos opciones sobre la mesa sirve tal cual**, así que se define una tercera.

**Por qué se descarta la actual** (`/sol-users/{user_id}/periodos/{periodo}/...`): expone el `_id` de Mongo en la URL, duplica la identidad (el `user_id` del path y el sujeto del JWT), tiene paths de 5 niveles antes del recurso real, no está versionada, y en la práctica ni la usa (ver deuda arriba).

**Por qué se descarta la de `Documento.md`** (`/api/v1/sire/conciliar`): son endpoints RPC sobre un recurso implícito. Pierde el direccionamiento multi-empresa y no escala a "N empresas × N periodos × 2 libros".

### Convención adoptada

```
/api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/<recurso>
                                                   libro ∈ ventas | compras
```

Tres reglas que la sostienen:

1. **La identidad del recurso es el RUC**, no el `_id` de Mongo. Es la clave natural del negocio, estable y legible en logs.
2. **El sujeto sale del JWT, nunca del path.** Una sola dependencia `resolver_empresa(ruc)` busca la empresa y verifica que el token la tenga concedida. Esto elimina de una vez el `user_id` redundante y los `tenant_id/cliente_id/cuenta_id` como query params.
3. **`libro` es un path param, no dos árboles de código.** Ventas y compras comparten el 90% de la lógica; duplicar rutas garantiza que divergan.

Las operaciones asíncronas devuelven `202 Accepted` con un `job_id` y se consultan en un recurso propio:

```
POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/propuesta/sincronizar → 202 {job_id}
GET  /api/v1/jobs/{job_id}                                                          → estado + progreso
```

### Contrato completo

| Método | Ruta (bajo `/api/v1`) | Acción | Dueño |
|---|---|---|---|
| `POST` | `/auth/login` | JWT a partir de RUC + usuario + clave SOL | A |
| `POST/GET/PUT` | `/empresas` · `/empresas/{ruc}` | Alta y configuración (rubro, descripción del negocio, credenciales) | A |
| `POST` | `/empresas/{ruc}/plan-cuentas` | Upload `.xlsx` del maestro de cuentas | B |
| `GET` | `/empresas/{ruc}/plan-cuentas` | Consulta del maestro | B |
| `POST/GET` | `/empresas/{ruc}/periodos` · `/{periodo}` | Ciclo de vida del periodo | A |
| `POST` | `…/libros/{libro}/propuesta/sincronizar` | Descarga propuesta SIRE → `202 job_id` | A |
| `GET` | `…/libros/{libro}/propuesta` | Comprobantes de la propuesta guardados | A |
| `POST` | `…/libros/{libro}/contasis` | Upload `.xlsx` Contasis → normaliza y guarda | B |
| `GET` | `…/libros/{libro}/contasis` | Registros Contasis normalizados | B |
| `POST` | `…/libros/{libro}/conciliacion` | Corre el motor → resumen + diferencias | B |
| `GET` | `…/libros/{libro}/conciliacion` | Último resultado de conciliación | B |
| `POST` | `…/libros/{libro}/aceptar` | Acepta la propuesta en SUNAT → `202 job_id` | A |
| `POST` | `…/libros/{libro}/reemplazar` | Genera archivo y reemplaza en SUNAT → `202 job_id` | A + B |
| `POST` | `…/registro` | Verifica ambos checks y genera el registro final | A |
| `POST` | `…/auditoria/extraccion` | Dispara scraping de PDFs → `202 job_id` | A |
| `POST` | `…/auditoria/analisis` | Dispara el agente IA → `202 job_id` | B |
| `GET` | `…/auditoria/reporte` | Tabla comparativa + glosas + URL del ZIP | B |
| `GET` | `/jobs/{job_id}` | Estado y progreso de cualquier job | A |

---

## 3. Estructura de código

Se mantiene `routes → services → db` (ya documentado en `capas.md`) y se agregan **dos capas** que hoy faltan y son las que habilitan tests:

```
app/
  api/v1/routes/          empresas, periodos, libros, conciliacion, auditoria, jobs, auth
  domain/                 ← NUEVO. Lógica pura, sin I/O, sin Mongo. Testeable con pytest solo.
    comprobante.py        modelo canónico + normalizadores (serie, número, RUC, montos)
    catalogos.py          tipos de documento y de identidad (de source/*.docx)
    conciliacion.py       el motor: recibe dos listas, devuelve un diff
    contasis_parser.py    xlsx FORMATO_VENTAS / FORMATO_ COMPRAS → Comprobante[]
    libro_electronico.py  Comprobante[] → archivo de reemplazo SUNAT
    jobs.py               contrato de trabajos asíncronos
  repositories/           ← NUEVO. Único lugar que habla con Mongo.
    empresas.py  periodos.py  comprobantes.py  conciliaciones.py  jobs.py
  services/               Orquestación: SUNAT, IA, scraping, jobs, reportes
    sunat/                cliente HTTP: auth, tickets, rvie, rce
  schemas/                Pydantic de request/response
  core/                   config, auth, encryption
tests/
  domain/                 tests sin I/O — donde vive el valor real
  fixtures/               apuntan a source/REGISTROS CASOS REALES/
```

La regla que hace que esto funcione: **`domain/` no importa nada de `app/db`, `app/repositories` ni `requests`.** Todo lo que entra son estructuras de datos. Es lo que permite testear el motor de conciliación contra los casos reales sin levantar Mongo ni tocar SUNAT.

> **Nota:** `source/` está en `.gitignore`, así que los archivos de casos reales no están versionados. Antes de empezar hay que decidir si se versionan copias anonimizadas en `tests/fixtures/` o si los tests se saltan cuando `source/` no está presente. Sin esa decisión, los tests del motor no corren en CI.

---

## 4. Modelo de datos

| Colección | Propósito | Notas |
|---|---|---|
| `empresas` | Evoluciona `sol_users`. RUC, usuario, clave cifrada, credenciales API SUNAT, rubro, descripción del negocio. | Se mantienen `tenant_id/cliente_id/cuenta_id` por compatibilidad, pero ya no se usan para resolver identidad. |
| `plan_cuentas` | Maestro PCGE por empresa: `cuenta`, `descripcion`, `tipo`, `analisis`, `centro_costos`. | Desde `source/CUENTAS CONTABLES.xlsx`, hoja `PLAN DE CUENTAS`. |
| `periodos` | Estado del periodo por libro: `{ventas: {estado, check, job_id}, compras: {…}}` | Reemplaza el `estado` plano actual. |
| `comprobantes` | Evoluciona `facturas`. **Un doc por comprobante**, con discriminadores `origen` (`sire`\|`contasis`) y `libro` (`ventas`\|`compras`). | Índice único: `(empresa_id, periodo, libro, origen, clave_conciliacion)`. |
| `conciliaciones` | Resultado de una corrida: resumen de totales, lista de diferencias tipificadas, estado. | Histórico — no se sobreescribe, se versiona por corrida. |
| `jobs` | `job_id`, tipo, estado, progreso, resultado, error, timestamps. | Cierra el hueco de `BackgroundTasks`. |
| `vector_global`, `vector_users` | Embeddings para RAG. | Sin cambios. |

### El modelo canónico `Comprobante`

Es **el contrato compartido entre A y B** y lo primero que hay que cerrar. Ambos lados (SIRE y Contasis) se normalizan a esta forma antes de compararse:

```
libro, origen, tipo_cp, serie, numero, tipo_doc_identidad, documento_contraparte,
razon_social, fecha_emision, fecha_vencimiento, moneda, tipo_cambio,
base_imponible, igv, exonerado, inafecto, isc, otros_tributos, total,
extra{}   ← campos propios de cada origen (cuenta contable, CAR SUNAT, etc.)
```

Los montos van en `Decimal`, no en `float` (ver §5). La normalización debe correr en la construcción del objeto, para que nadie aguas abajo tenga que volver a limpiar los campos.

### Mapeo de orígenes

- **Contasis** (hojas `FORMATO_VENTAS` / `FORMATO_ COMPRAS `): cabeceras en 3 filas combinadas, fila de tipos (`dd/mm/yyyy`, `02 CARACTERES`, `(15,2) NUMERICO`) y luego datos. En los archivos reales el offset **varía**: `RCV JOAQUISAN` empieza en fila 4, `RV CORPORACION` en fila 5, y la hoja `JULIO` del mismo archivo en fila 3. El parser debe **detectar la fila de inicio buscando la fila de tipos**, no asumir un número fijo. Trae columnas propias de Contasis que SUNAT no tiene: `CONDICION CONTADO/CREDITO`, `CODIGO CENTRO DE COSTOS`, `CUENTA CONTABLE BASE IMPONIBLE`, `CUENTA CONTABLE TOTAL`, `REGIMEN ESPECIAL` → van a `extra{}`.
- **SIRE**: la hoja `Hoja2` de `RCV JOAQUISAN 062026.xlsx` es una descarga real de la propuesta SUNAT (`Ruc, Razon Social, Periodo, CAR SUNAT, Tipo CP/Doc., Serie del CDP, Nro CP, BI Gravada, IGV / IPM, Total CP, …`). Es la referencia autoritativa de los nombres de campo.

### Catálogos de códigos

`source/CODIGOS DE TIPOS PARA CONTASIS.docx` guarda las tablas como **imágenes**, no como texto — extraerlas requiere abrir el `.docx` como ZIP y leer `word/media/`. Ya se transcribieron ampliando las capturas, y hay dos detalles que una lectura rápida se come:

- **No existe el código 47.** La lista salta de 46 a 48. Transcribir de corrido corre toda la banda 48–51 en uno (queda `48 CONSTANCIA DE DEPÓSITO` cuando en realidad es `49`).
- Los códigos **55** (`BVME TRANS FERROV PASAJEROS`) y **56** (`COMPROBANTE PAGO SEAE`) se pierden fácil porque están entre el 54 y el salto al 87.

**Tipo de documento de identidad:** `0` otros · `1` DNI · `4` carnet de extranjería · `6` RUC · `7` pasaporte · `A` cédula diplomática.

**Tipo de comprobante** (los relevantes para este sistema): `01` factura · `03` boleta de venta · `07` nota de crédito · `08` nota de débito · `12` ticket máquina registradora · `14` recibo serv. públicos · `87`/`88` notas especiales · `97`/`98` notas de no domiciliado. El catálogo completo son ~54 entradas y va transcrito a `domain/catalogos.py` como constantes.

---

## 5. El motor de conciliación (la pieza crítica)

Vive en `domain/conciliacion.py`. Recibe `list[Comprobante]` de cada origen y devuelve un diff. **No toca Mongo ni SUNAT.**

**Clave de match:** `tipo_cp + serie_normalizada + numero_normalizado + documento_contraparte_normalizado`.

La normalización es donde están los bugs, y los datos reales de `source/` lo demuestran:

- **Serie con ceros inconsistentes:** `00B001` (Contasis) vs `B001` (SIRE); `EB01` vs `00EB01`. Quitar ceros a la izquierda es seguro porque SUNAT rellena a ancho fijo de forma inconsistente entre endpoints.
- **Errores de tipeo en producción:** en `RC CORPORACION 2026 OKI.xlsx`, hoja MAYO, aparece `0S898` donde el resto del archivo dice `00S898` — ese converge al normalizar. Pero también aparece `005060` donde debería decir `00S060`: ahí la `S` se tipeó como `5`, y eso **no** converge. Debe salir reportado como diferencia real; el motor no puede adivinarlo.
- **Número con ceros a la izquierda:** comparar como entero cuando sea numérico. Ojo con openpyxl, que devuelve `116472.0` (float) para celdas numéricas.
- **Documento sucio:** `20432405525` con carácter invisible al final. Un `strip()` normal no lo limpia; hay que filtrar a solo dígitos.
- **Montos con precisión distinta:** Contasis guarda `44.067796610169495` (resultado de dividir el total entre 1.18 sin redondear), SUNAT reporta `44.07`. **Usar `Decimal` cuantizado a 2 decimales y comparar con tolerancia de ±0.01 por comprobante**, más un umbral configurable a nivel de totales. Comparar flotantes con `==` garantiza que nada cuadre nunca.
- **Filas basura:** en `RC CORPORACION`, hoja AGOSTO, hay una fila final con `#N/A` y ceros. El parser debe descartar filas sin fecha o sin serie.
- **Documento de identidad ausente:** las boletas a "VARIOS CLIENTES" traen `-` en tipo y número en la descarga SIRE, y `1 / 11111111` en Contasis. Son lo mismo y no deben contar como diferencia de contraparte.

**Salida tipificada** — cada diferencia cae en una de estas categorías, y esto es exactamente lo que el frontend renderiza:

| Tipo | Significado |
|---|---|
| `SOLO_EN_CONTASIS` | Comprobante que la empresa registró y SUNAT no propuso |
| `SOLO_EN_SIRE` | SUNAT propuso algo que la empresa no tiene registrado |
| `DIFERENCIA_MONTO` | Match de clave, pero base/IGV/total difieren más que la tolerancia |
| `DIFERENCIA_FECHA` | Match de clave, fecha de emisión distinta |
| `DIFERENCIA_CONTRAPARTE` | Match de clave, documento o razón social distintos |
| `DUPLICADO` | La misma clave aparece más de una vez en un origen |

Más el resumen: totales por origen, conteos, y el veredicto `MATCH` \| `DIFERENCIAS` que decide si el flujo va a *aceptar* o a *reemplazar*.

### Fixture de oro

`source/REGISTROS CASOS REALES/RCV JOAQUISAN 062026.xlsx` tiene **los dos lados del mismo periodo en un solo archivo**: `FORMATO_VENTAS` (Contasis, 409 filas) y `Hoja2` (descarga SIRE, 362 filas), ambos RUC `20608997106`, periodo `202606`. Es el caso de prueba del motor y debe estar disponible para los tests desde el día 1. La diferencia de conteo (409 vs 362) no es un error del parser: es precisamente el tipo de discrepancia que el motor debe explicar.

---

## 6. Riesgo #1: los endpoints de escritura del SIRE

El código actual solo **lee**, usando el endpoint JSON paginado `/propuesta/{periodo}/busqueda`. Aceptar y reemplazar son operaciones **asíncronas por ticket**: se envía la petición, SUNAT devuelve un `numTicket`, se consulta el estado en bucle y al terminar se descarga un archivo de reporte.

No tenemos confirmados los paths exactos ni el formato del archivo de reemplazo — `Documento.md` mismo lo deja como pendiente de investigación. Por eso:

- **Tarea 0 del plan (spike de A, bloqueante, 1–2 días):** contra el manual oficial de SUNAT y el ambiente de pruebas, confirmar (a) paths de `exportapropuesta`, `aceptapropuesta`, `reemplazapropuesta` y consulta de ticket para RVIE y RCE; (b) formato exacto del archivo de reemplazo (TXT delimitado, nombre del archivo, encoding, si va zipeado); (c) si el flujo requiere `generar registro` como paso separado.
- **Mitigación de diseño:** todos los paths salen de configuración (`Settings`), nunca hardcodeados. El módulo `services/sunat/tickets.py` implementa el patrón "enviar → poll → descargar" de forma genérica, así que la lógica de polling se escribe y se testea **sin depender** del resultado del spike.
- Mientras el spike no cierre, B avanza al 100% en su carril: no depende de SUNAT en absoluto.

---

## 7. División del trabajo

El corte busca minimizar colisiones: **A es dueño de todo lo que habla con SUNAT; B es dueño de todo lo que habla con datos.** Se toca backend en ambos casos; el frontend de B es una fase posterior y va sin detalle.

### Fase 0 — Juntos (2–3 días, bloqueante)

Nadie se separa hasta que esto esté mergeado:

1. Crear la estructura `app/api/v1/`, `app/domain/`, `app/repositories/`.
2. **Definir `domain/comprobante.py`**: el modelo canónico, los enums `Libro`/`Origen`/`TipoDiferencia`, y las funciones de normalización. Es el contrato; si cambia después, ambos rehacen trabajo.
3. Definir `domain/jobs.py` (estados, tipos, forma del progreso) y la respuesta de `GET /jobs/{job_id}`.
4. Transcribir `domain/catalogos.py` desde las imágenes del `.docx` (ver §4 — ojo con el código 47 inexistente).
5. Decidir qué se hace con los fixtures, dado que `source/` está en `.gitignore`.
6. Arreglar la deuda barata: `GEMINI_API_KEY` dentro de `Settings`, CORS con orígenes explícitos, colapsar `get_db`/`get_user_db`.
7. Agregar `pytest` a las dependencias de desarrollo (hoy no está) y acordar: PRs pequeños, un solo dueño por archivo, `ruff` en CI.

### Persona A — Eje SUNAT

| # | Tarea | Entregable |
|---|---|---|
| A0 | **Spike API SIRE** (ver §6) | Documento con paths, formatos y ejemplos de respuesta confirmados |
| A1 | `services/sunat/auth.py` — extraer el OAuth existente de `sire_service.py:15` y `:131`, generalizar el retry en 401 | Cliente de auth reutilizable |
| A2 | `services/sunat/tickets.py` — patrón enviar → poll → descargar, genérico | Con tests usando respuestas mockeadas |
| A3 | `services/sunat/rvie.py` + `rce.py` — propuesta, aceptar, reemplazar, registro, para ambos libros | Cliente SIRE completo |
| A4 | `services/jobs.py` + `repositories/jobs.py` + `GET /jobs/{job_id}` | Progreso consultable desde el frontend |
| A5 | **Rutas de propuesta y aprobación** (`sincronizar`, `aceptar`, `reemplazar`, `registro`) — soportando `libro=ventas` y `libro=compras` | Fase 1 operativa punta a punta |
| A6 | **Quitar el filtro de series `F`/`E`** ([sire_service.py:60](app/services/sire_service.py:60)) y el `tipo_operacion="compras"` hardcodeado | Boletas y notas de crédito/débito dejan de perderse |
| A7 | Migrar `sol_users` → `empresas`; `resolver_empresa(ruc)` desde el JWT; retirar `tenant_id/cliente_id/cuenta_id` como query params | Deuda de autorización cerrada |
| A8 | **Fase 2 — descarga de PDFs**: extender `scraping_sunat.py` reusando `_hacer_login`, iterando facturas y boletas + sus notas, guardando en `data/{libro}/{año}/{mes}/{tipo}/` | Scraper de PDFs reportando progreso a `jobs` |

### Persona B — Eje Datos, Conciliación y Auditoría

| # | Tarea | Entregable |
|---|---|---|
| B1 | `repositories/` — empresas, periodos, comprobantes, conciliaciones | Único punto de acceso a Mongo |
| B2 | `domain/contasis_parser.py` — parser del xlsx con **detección de fila de inicio** | Tests contra los 4 archivos reales de `source/` |
| B3 | **`domain/conciliacion.py` — el motor** (ver §5) | Tests contra el fixture de oro JOAQUISAN |
| B4 | Rutas de Contasis (`POST/GET …/contasis`) y de conciliación (`POST/GET …/conciliacion`) | Conciliación consultable |
| B5 | `POST …/plan-cuentas` — parser de `CUENTAS CONTABLES.xlsx` (2.883 filas) → colección `plan_cuentas` | Maestro de cuentas cargable |
| B6 | `domain/libro_electronico.py` — `Comprobante[]` → archivo de reemplazo en el formato SUNAT | **Contrato con A:** B produce los bytes, A los sube. Depende del spike A0 para el formato. |
| B7 | **Fase 2 — IA de auditoría**: alimentar `extraer_datos_factura` ([analisis_ia.py:170](app/services/analisis_ia.py:170)) con texto del PDF + `plan_cuentas` + descripción del negocio, en lugar de solo el `raw_data` de SIRE | Glosas con contexto real |
| B8 | **Reporte de auditoría**: tabla comparativa + glosas + ZIP de respaldos, extendiendo `export_service.py` | `GET …/auditoria/reporte` |
| B9 | Tests de integración del flujo completo con SUNAT mockeado | Suite verde en CI |
| B10 | **Frontend (fase posterior)** | Ver §8 |

### Secuencia y dependencias

```
Fase 0 (juntos) ──┬── A: A0 spike ── A1 ── A2 ── A3 ── A5 ─┬── A8 (Fase 2)
                  │        A4, A6, A7 en paralelo          │
                  └── B: B1 ── B2 ── B3 ── B4 ── B5 ───────┴── B6 ── B7 ── B8 ── B9
```

Único punto de sincronización real: **B6 necesita el formato de archivo que sale de A0.** Todo lo demás corre en paralelo. Si A0 se atrasa, B tiene B1–B5 y B7–B8 para seguir avanzando.

---

## 8. Frontend (vistazo, sin detalle)

React + TypeScript en Vercel, contra los endpoints de §2. No se desarrolla en esta etapa; queda como fase de B cuando el backend cierre. Cinco pantallas:

1. **Configuración de empresa** — datos, credenciales, descripción del negocio, upload del maestro de cuentas.
2. **Periodos** — grilla año/mes con el estado de ventas y compras por separado.
3. **Conciliación** (la pantalla central) — upload del Excel de Contasis, resumen de totales lado a lado, y la tabla de diferencias agrupada por los tipos de `TipoDiferencia` de §5. Los dos botones de acción salen del veredicto: *Aceptar propuesta* si `MATCH`, *Reemplazar* si `DIFERENCIAS`.
4. **Auditoría** — disparo de extracción y de IA, con barra de progreso alimentada por `GET /jobs/{job_id}`.
5. **Reporte** — tabla comparativa con glosas y descarga del ZIP.

El backend queda listo para esto por diseño: `TipoDiferencia` es un enum estable (la tabla se renderiza sin lógica en el cliente) y `jobs` da el progreso sin polling artificial sobre endpoints de negocio.

---

## 9. Verificación

**Dominio (sin I/O, es el que más importa):**

```bash
uv run pytest tests/domain -v
```

- El parser lee los 4 archivos reales de `source/` sin excepciones y sin filas basura.
- El motor conciliado sobre el fixture JOAQUISAN: los comprobantes que existen en ambos lados matchean, y la diferencia de 409 vs 362 filas queda **explicada** por diferencias tipificadas — no por fallos de normalización. Este es el criterio de aceptación de B3.
- Casos de normalización explícitos: `00B001` == `B001`, `0S898` == `00S898`, `44.067796610169495` == `44.07`, y `005060` != `00S060` (debe reportarse como diferencia).

**Integración con SUNAT mockeado:**

```bash
uv run pytest tests/integration -v
```

Cubre el flujo por ticket (enviar → poll → descargar) y los dos caminos de la conciliación (aceptar vs reemplazar), con `responses`/`respx` sobre el cliente HTTP.

**Punta a punta contra SUNAT real**, en el ambiente de pruebas, con un RUC de prueba y un periodo cerrado:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 9007 --reload
```

Secuencia manual sobre `http://127.0.0.1:9007/docs`:

1. `POST /api/v1/auth/login` → JWT.
2. `POST /api/v1/empresas/{ruc}/plan-cuentas` con `CUENTAS CONTABLES.xlsx` → verificar el conteo de cuentas cargadas.
3. `POST …/libros/ventas/propuesta/sincronizar` → `job_id`; seguir en `GET /api/v1/jobs/{job_id}` hasta `completado`.
4. `POST …/libros/ventas/contasis` con `RCV JOAQUISAN 062026.xlsx`.
5. `POST …/libros/ventas/conciliacion` → inspeccionar el veredicto y las diferencias.
6. Según veredicto: `POST …/aceptar` o `POST …/reemplazar` → confirmar que SUNAT devuelve ticket y que el job llega a `completado`.
7. Repetir 3–6 con `libro=compras`, luego `POST …/registro`.
8. Fase 2: `POST …/auditoria/extraccion`, `POST …/auditoria/analisis`, `GET …/auditoria/reporte`.

**Antes de cada PR:**

```bash
uv run ruff check app tests
```
