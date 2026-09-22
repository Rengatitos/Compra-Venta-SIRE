# Captura documental adaptada a SIRE

## Arquitectura y persistencia

Se reutilizan FastAPI, MongoDB, React, la identidad de empresa y el JWT del backend.
El cliente WhatsApp reenvía el formulario original a `/api/v1/captura/whatsapp`.
La API valida firma, cuenta Twilio, destino y teléfono autorizado. No ejecuta OCR en el webhook.

Una transacción guarda evento, sesión, lote y documentos. El identificador del evento es
`MessageSid`; las entregas repetidas devuelven la respuesta persistida. Los índices se crean
de forma idempotente y la captura requiere transacciones; no se degrada a escrituras parciales.

Colecciones nuevas: `captura_phones`, `captura_company_settings`, `captura_sessions`,
`captura_events`, `captura_batches`, `captura_documents`, `captura_identities`,
`captura_audit`, `captura_notifications` y `captura_matches`.
Los bloques OCR, campos, metadata e ítems se conservan dentro del documento para actualización atómica.
Los periodos son `YYYYMM`, igual que SIRE.

**Confirmar un documento capturado no modifica las propuestas descargadas de SUNAT.**
El inventario conserva documentos y pagos con su origen propio. La exportación Contasis
existente continúa usando el registro SIRE; la nueva captura exporta CSV con medio de pago
y operación, incluida la información de un pago vinculado explícitamente.

## Procesamiento

Mongo actúa como outbox durable. Beat despacha pendientes cada cinco segundos a Redis/Celery.
Una caída de Redis no pierde documentos aceptados. Los workers usan leases, reservas de
despacho y reintentos; un documento fallido no detiene el lote.

Flujo: descarga autenticada de Twilio → validación del archivo → almacenamiento UUID →
metadata → OCR/QR local → clasificación ponderada → extracción → periodo → validación.
Los archivos sólo pueden descargarse de las rutas Twilio esperadas; una redirección CDN
no recibe las credenciales Basic Auth. Se limitan bytes, píxeles y páginas.

El OCR se guarda y reutiliza por documento/archivo. Cada página se reconoce una sola vez
en la ejecución normal; los extractores comparten esos bloques. Un reproceso explícito
crea otra generación. Si un proceso muere antes de persistir su OCR, puede repetir la inferencia.
La idempotencia garantizada corresponde a la recepción, no a una única ejecución física
frente a cualquier fallo del proceso.

RapidOCR/ONNX trabaja localmente, con español (`OCR_LANGUAGE=es`). OpenCV decodifica QR
y ajusta imágenes grandes; se respeta orientación EXIF. Los originales no se modifican.
La interfaz `StorageProvider` admite incorporar otro almacenamiento; sólo `local` está implementado.

## Extracción y fechas

Las reglas ponderadas distinguen el título de una nota de crédito de una referencia a factura.
Se incluyen los tipos SUNAT solicitados y Yape, Plin, POS, transferencias, depósitos y liquidaciones.
Un documento ambiguo queda como `UNKNOWN` y requiere revisión.

El extractor común conserva evidencia por campo: valor, estado, confianza, texto, página y
coordenadas. Reconoce campos rotulados, números de documento, importes, referencias y tablas
de ítems con columnas identificables. No presupone cobertura fiable de todos los diseños de
cada proveedor. Los campos ausentes, vacíos, ilegibles o no aplicables conservan `null` y
su estado separado. No hay APIs generativas ni un clasificador entrenado sin corpus etiquetado.

- `received_at`: momento de recepción del webhook o carga web.
- `document_date`: fecha del comprobante extraída con confianza suficiente o corregida.
- `metadata_date`: evidencia secundaria del archivo, cuando existe.
- `accounting_period`: periodo de clasificación contable.
- `twilio_received_at`: `null`; el webhook estándar no aporta una fecha verificable del
  instante de recepción interno de Twilio. `received_at_source=WEBHOOK` lo hace explícito.

La fecha documental nunca se rellena silenciosamente con la de ingreso o la metadata.
OCR con confianza ≥ 0.85 prevalece sobre metadata posterior. En un lote, una fecha fuera
del periodo produce `MISMATCH`; mover o mantener el periodo requiere intervención auditada.
Sin fecha OCR, la metadata puede proponer periodo, y un lote puede conservar su periodo
objetivo, siempre con observación. Un documento individual sin evidencia pide periodo.

La validación usa Decimal, tolerancias, RUC, importes, aritmética y estados por campo.
SHA-256 detecta archivos repetidos; la huella de RUC/tipo/serie/número/fecha/total señala
posibles repeticiones documentales. No se elimina automáticamente ningún original.

## Conversaciones y revisión

Cada sesión está ligada a empresa y teléfono, con estado, lote/documento actual, periodo
seleccionado y caducidad. Los comandos tienen handlers separados. Las sesiones expiradas
no descartan referencias a documentos aún pendientes.

Durante un lote sólo se acusa recepción. Tras `FIN`, el resumen llega al terminar todos
los archivos, incluidos los fallidos. Las correcciones complejas abren React.
`CONFIRMAR VALIDOS` confirma únicamente documentos `READY`; las observaciones quedan pendientes.

La edición web requiere `revision` y responde 409 ante cambios concurrentes. Las correcciones
vuelven a validar; los valores anteriores/nuevos quedan en auditoría. La conciliación
propone coincidencias con score ≥ 85, pero el usuario debe vincularlas explícitamente.
Los documentos confirmados o conciliados no se editan silenciosamente.

## Seguridad y operación

Los endpoints del inventario toman la empresa del JWT, no de un parámetro del cliente.
Los archivos se consultan mediante peticiones autenticadas y blobs; el directorio no se
publica y el JWT no se pone en enlaces del navegador. El webhook usa firma Twilio.
Las tarjetas se enmascaran antes de persistir OCR; se conserva únicamente last4 en los campos.
Los logs documentales contienen IDs técnicos y estados, no textos OCR, teléfonos ni secretos.

Una notificación aceptada por Twilio cuya respuesta se pierda puede repetirse al reintentar.
Fuera de la ventana de atención de WhatsApp se necesita una plantilla aprobada; un fallo de
notificación no impide consultar el resultado en React. Las credenciales/configuración de
la cuenta y el túnel deben validarse con una prueba real antes de desplegar.

## API

Base: `/api/v1/captura`.

- `POST /whatsapp`: recepción firmada desde el cliente.
- `GET/POST /phones`: autorización del teléfono.
- `GET/POST /documents`, `GET/PATCH /documents/{id}`.
- `POST /documents/{id}/{confirm,resolve,cancel,reprocess,move-period}`.
- `GET /documents/{id}/file`: original autenticado.
- `GET /periods`, `GET /periods/{year}/{month}/{documents,summary}`.
- `GET/POST /batches`, `GET /batches/{id}`, `GET /batches/{id}/documents`.
- `POST /batches/{id}/{close,confirm}`.
- `POST /reconciliation/run`, `POST /reconciliation/{id}/confirm`.
- `GET /export?period=YYYYMM`: CSV de confirmados.

Observados y duplicados son filtros de `/documents`. Los endpoints previos SIRE no cambian.

## Archivos y pruebas

- `app/domain/captura/`: reglas puras, modelos, layout, periodos y validaciones.
- `app/services/captura/`: recepción, conversación, almacenamiento, OCR, pipeline y revisión.
- `app/repositories/captura.py`: colecciones, índices y transacciones.
- `app/api/v1/routes/captura.py`: API integrada.
- `app/workers/captura.py`: tareas Celery y recuperación.
- `frontend/src/features/captura/`: inventario React.
- `tests/captura/`: fixtures sintéticas y pruebas.

```bash
uv run pytest tests/captura
npm run typecheck --prefix frontend
npm test --prefix frontend
```

Pruebas optativas:

- `CAPTURA_TEST_OCR=1`: prueba con motor real y PDF sintético.
- `CAPTURA_TEST_MONGO_URI=mongodb://127.0.0.1:27019/?directConnection=true`: integración
  con replica set local temporal. Crea `captura_test_<uuid>` y elimina sólo esa base.
  Nunca usa la conexión de producción.

Referencias: [firmas Twilio](https://www.twilio.com/docs/usage/webhooks/webhooks-security),
[RapidOCR](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/),
[Celery](https://docs.celeryq.dev/en/stable/userguide/tasks.html).
