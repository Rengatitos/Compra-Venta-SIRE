# Costos del canal de captura: PWA vs WhatsApp vs CRM

Costeado para el escenario real del cliente: 10 empresas fijas, Android, zonas rurales. La comparación de canal está en [Canal_WhatsApp_vs_PWA.xlsx](../../../Sire_Docs/Canal_WhatsApp_vs_PWA.xlsx) y los plazos en [cronograma.md](cronograma.md).

## Supuestos

| Supuesto | Valor | Origen |
|---|---|---|
| Empresas | **10, fijas** | Dato del cliente. No hay escenario de crecimiento |
| Comprobantes por empresa-mes | **50** | Medido: 61 y 47 compras en los periodos 202608 y 202607 (`logs/automat_api.log`) |
| Volumen total | **500 comprobantes al mes** | 10 × 50 |
| Tipo de cambio | **S/ 3,37 por USD** | Promedio de septiembre de 2026 |
| Tarifa de trabajo | S/ 80 por hora | Referencial, para comparar construcción contra operación |
| Precios de infraestructura | Listas de Hetzner y Google Cloud sin impuestos | `Costos_RAG_VPS.md` y `Costos_Despliegue_GCP.docx` |

## Infraestructura: todo compartido en una sola máquina

Sire y el bot no necesitan máquinas separadas. Comparten base de datos, proxy HTTPS, respaldos, dominio y despliegue, y la PWA se sirve como estáticos desde el mismo Caddy que ya sirve el panel web.

| Opción | Qué corre | USD/mes | **S/ mes** |
|---|---|---|---|
| **VPS Hetzner CAX21, todo compartido** | Sire (API + Chromium + MongoDB) + bot + panel web + PWA | 15,59 | **S/ 53** |
| GCP e2-medium, todo compartido | Lo mismo, en Google Cloud | 32,00 | S/ 108 |
| GCP e2-small (Sire) + Railway (bot) | Dos proveedores, dos despliegues, dos facturas | 41,00 | S/ 139 |

El desglose de la VPS: CAX21 (4 vCPU ARM, 8 GB, 80 GB NVMe, 20 TB de tráfico) a USD 12,49, IPv4 a 0,60 y respaldos automáticos a 2,50. Toda la pila corre en ARM64 sin cambios: Chromium, MongoDB, Node y `sharp` tienen binarios nativos.

**El hallazgo que ordena este documento: con la VPS compartida, sumar el bot no cuesta infraestructura adicional.** La plataforma entera —Sire, el bot y la PWA— cuesta S/ 53 al mes, menos que los S/ 58 que ya estaban presupuestados solo para Sire en una `e2-small` de Google Cloud. El bot cabe en la holgura que se gana al pasar de 2 GB a 8 GB de RAM.

Lo que se pierde al salir de Google Cloud, en honor a la verdad: el crédito inicial de USD 300, la región cercana a Perú y los respaldos gestionados. **Y un riesgo que ya está anotado en `Costos_RAG_VPS.md`: que el portal SOL de SUNAT trate distinto al tráfico que llega desde Europa.** Eso se prueba en un día y conviene probarlo antes de migrar, no después.

Las imágenes ocupan poco: 500 fotos comprimidas a ~200 KB son unos 100 MB, y se purgan a los 30 días.

## Gemini

Único costo que sí depende del volumen, y del flujo más que del canal:

| Flujo | Por comprobante | 500 al mes |
|---|---|---|
| Directo: extracción + una confirmación (el recomendado para zonas rurales) | S/ 0,019 | **S/ 10** |
| Con chat completo: extracción + tres turnos del agente con memoria | S/ 0,041 | S/ 21 |

Presupuestar **S/ 21** y esperar la mitad. La tarifa de Gemini 3.6 Flash (USD 0,75 y 3,75 por millón de tokens) **es promocional hasta el 31-dic-2026 y se duplica el 1-ene-2027**: desde enero, entre S/ 20 y S/ 42.

## Comparación de las tres opciones

Costo mensual de la plataforma completa, con infraestructura compartida en la VPS y 500 comprobantes:

| Opción | Infra | Gemini | Canal | **Total mensual** | Por comprobante |
|---|---|---|---|---|---|
| **A — PWA propia (recomendada)** | S/ 53 | S/ 21 | S/ 0 | **S/ 74** | **S/ 0,15** |
| B — WhatsApp Business API | S/ 53 | S/ 21 | S/ 55 | **S/ 129** | S/ 0,26 |
| C — CRM (Kommo) + WhatsApp | S/ 53 | S/ 21 | S/ 139 | **S/ 213** | S/ 0,43 |

**Opción A.** La PWA no tiene costo de canal: se sirve desde la misma máquina. Sin tiendas no hay USD 99 de Apple ni USD 25 de Google Play, ni revisiones, ni la regla de los 12 probadores.

**Opción B.** Los S/ 55 son 1.500 mensajes salientes al mes, de los cuales 500 resultan cobrables una vez agotados los 1.000 gratis por número (S/ 13 a Meta desde el 1-oct-2026), más el proveedor: Twilio cobra USD 0,005 por mensaje enviado y recibido, unos S/ 42. Con 360dialog serían S/ 178 fijos, peor a este volumen. No incluye lo que no se factura: crear la cuenta de Meta Business, verificar el negocio, registrar método de pago y esperar la aprobación de plantillas.

**Opción C.** Kommo Advanced son USD 25 por usuario/mes con permanencia mínima de 6 meses, más el markup sobre los mensajes. No sustituye nada: no lee el voucher, no normaliza montos ni fechas, no resuelve duplicados y no habla con Sire. El bot se construye igual. Descartada.

## Construcción

| Bloque | Horas | A S/ 80/h |
|---|---|---|
| Despliegue de la plataforma (Sire + bot + PWA en la misma máquina) | 10 | S/ 800 |
| Tronco común: pruebas con fotos reales, 3 endpoints en Sire, vinculación, verificación end-to-end | 19 | S/ 1.520 |
| PWA: cámara y compresión, cola offline, confirmación e historial, piloto | 14 | S/ 1.120 |
| **Total** | **43** | **S/ 3.440** |

Repartido entre dos personas en 10 días hábiles: unas 25 horas para Cinver y 18 para Camila, alrededor de 2 horas diarias cada uno.

La ruta WhatsApp costaría 36 horas propias —se ahorra la PWA pero se escribe la capa de canal— y añade plazos de terceros que no entran en dos semanas.

## Primer año

| Ruta | Construcción | Operación (12 meses) | **Total año 1** |
|---|---|---|---|
| **PWA, infraestructura compartida** | S/ 3.440 | S/ 888 | **S/ 4.328** |
| WhatsApp, infraestructura compartida | S/ 2.880 | S/ 1.548 | S/ 4.428 |

## Conclusión

**Con 10 empresas fijas y todo compartido en una VPS, el canal propio cuesta S/ 74 al mes: 15 céntimos por comprobante procesado.** Es la mitad que WhatsApp y la tercera parte que un CRM, y el bot no añade una sola máquina.

La diferencia en el primer año entre PWA y WhatsApp sigue siendo pequeña en dinero. Lo que decide es lo que no aparece en la tabla: WhatsApp depende de una cuenta de Meta que hoy no existe, con verificaciones y aprobaciones que no controlamos, dentro de un plazo de dos semanas.

## Fuentes

- `Costos_RAG_VPS.md` y `Costos_Despliegue_GCP.docx` — costos de infraestructura ya elaborados para este proyecto
- [Hetzner Cloud pricing](https://comparedge.com/tools/hetzner/pricing) — planes CAX tras el ajuste de junio de 2026
- [Pricing on the WhatsApp Business Platform](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing) y [cambios para mensajes de servicio y utility](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/non-template-messages) — Meta
- [Service Message Charging Starts October 1, 2026](https://360dialog.com/blog/whatsapp-service-message-charging-october-2026/) — 360dialog
- [WhatsApp Messaging Pricing](https://www.twilio.com/en-us/whatsapp/pricing) — Twilio
- [Kommo CRM precios 2026](https://www.eligetucrm.com/blog/kommo-precios-2026)
- [Gemini 3 Flash API Pricing](https://tokencost.app/models/gemini-3-flash)
