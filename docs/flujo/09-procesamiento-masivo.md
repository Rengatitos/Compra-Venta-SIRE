# Flujo — Procesamiento masivo de empresas

El contador elige empresas y periodos, inicia el proceso y se desentiende: todo corre en el servidor y al final le llega un correo con el ZIP.

```
Registro de empresas
  → selección de empresas y periodos (panel /empresas)
  → una solicitud con un item por empresa × periodo
  → por item, en la cola: credenciales (si faltan) → SIRE compras → SIRE ventas
      → comprobantes de compras → comprobantes de ventas → IA compras → IA ventas
  → empaquetado: Excel y comprobantes por carpeta, ZIP
  → correo al contador y a los correos de cada empresa
```

## 1. Selección

En el panel general (`/empresas`) se marcan empresas (una, varias o «Seleccionar todas»), se elige un mes, un rango de meses o todos los periodos registrados, y si se clasifica con IA. «Procesar» llama a [POST /solicitudes](../endpoints/solicitudes.md).

## 2. Pasos de cada item

Cada paso es un trabajo de la [cola durable](../arquitectura/cola.md) con `solicitud_id`. Cuando uno queda cerrado (completado, o fallido sin más reintentos), el worker llama a `solicitudes_service.al_terminar`, que encola el siguiente del mismo item. Items de empresas distintas avanzan en paralelo; los de una misma empresa se turnan en su carril SOL.

- **Credenciales**: solo si la empresa no tiene client_id/clave del API SUNAT. Usa [credenciales_sunat_service](../../app/services/credenciales_sunat_service.py).
- **SIRE compras y ventas**: la propuesta por la API SIRE, igual que la descarga manual. Si compras cambia, encadena la consulta de detracciones. **Si falla, el item se corta**: sin propuesta no hay comprobantes que procesar y el resto de pasos queda «omitido».
- **Comprobantes**: detalle y PDF desde el portal SOL. El trabajo repite rondas de `SUNAT_MAX_COMPROBANTES` mientras queden pendientes y haya avance.
- **IA**: [clasificación automática](#3-clasificación-automática), por rondas de `CLASIFICADOR_MAX_COMPROBANTES`.

Un fallo que no es de SIRE deja el item «con observaciones» pero sigue con el resto de pasos. Cada fallo pasajero se reintenta solo, con espera creciente (ver [reintentos](../arquitectura/cola.md#reintentos)).

## 3. Clasificación automática

- Candidatos: comprobantes con glosa **sin código válido**. Es decir, sin clasificación, sin cuenta base o en «requiere revisión» (cuya cuenta no pasa al Excel). Los que ya tienen un código válido no se vuelven a mandar.
- Cada intento queda en el comprobante: `clasificacion_estado` (`clasificado`, `sin_codigo`, `error`, `error_persistente`), `clasificacion_intentos`, `clasificacion_ultimo_error` y `clasificacion_ultimo_intento_en`.
- Tras `CLASIFICADOR_MAX_INTENTOS_COMPROBANTE` intentos sin código, el comprobante pasa a `error_persistente` y la clasificación automática deja de insistir: queda para revisión manual.
- Si al terminar una ronda quedan comprobantes reintentables, el trabajo lanza un error transitorio y la cola lo vuelve a correr más tarde. En su último intento devuelve lo conseguido.

## 4. Archivos y ZIP

Cuando todos los items terminan, un único trabajo `empaquetado` ([empaquetado_service.py](../../app/services/empaquetado_service.py)) escribe `DESCARGA_AAAA-MM-DD.zip` con una carpeta por item:

```
20123456789_2026-08_2026-09-27/
├── Ventas/Reporte_Ventas.xlsx
├── Compras/Reporte_Compras.xlsx
├── Comprobantes/
│   ├── Facturas/   COMPRA_{rucEmisor}_{serie-numero}.pdf, VENTA_…
│   ├── Boletas/
│   ├── Notas de crédito/ · Notas de débito/ (si hay)
│   └── Otros/
└── observaciones.txt   (si algo faltó)
```

- La carpeta es `RUC_AAAA-MM_AAAA-MM-DD`: el periodo y el día, en Lima, de la última descarga SIRE completada.
- El Excel es el de la plantilla oficial, generado desde Mongo sin volver a llamar a SUNAT; el destino de compras se deduce igual que en la exportación.
- Los PDF se leen de donde ya los dejó el scraping y se escriben directamente en el ZIP.
- `observaciones.txt` explica lo que no está: tipo de cambio pendiente, PDF que SUNAT no dio o pasos fallidos.

## 5. Correo

Un trabajo `envio_correo` ([correo_service.py](../../app/services/correo_service.py)) escribe por SMTP a:

- quien pidió la solicitud, con todas las empresas;
- cada correo de `correos_notificacion` de las empresas incluidas, **solo con las suyas**, en un ZIP aparte.

El correo avisa del fin y resume cada etapa (SIRE, comprobantes, IA, archivos) y el estado de cada empresa y periodo. El ZIP va adjunto hasta `CORREO_MAX_ADJUNTO_MB`; si pesa más, va un enlace firmado ([GET /descargas/{token}](../endpoints/solicitudes.md)) que caduca a los `DESCARGA_ENLACE_DIAS`.

Reglas del envío:

- Un destinatario fuera de `CORREO_DESTINATARIOS_PERMITIDOS` queda «bloqueado» y no se le escribe. En local solo se admite el correo de pruebas.
- Sin `SMTP_HOST`, o con la contraseña SMTP rechazada, el envío queda fallido sin reintentarse.
- Un corte de red se reintenta solo para los correos que no salieron.

Cada envío queda en la solicitud y se lista en [GET /correos/envios](../endpoints/solicitudes.md): correo, empresas asociadas, periodos procesados, fecha y estado.
