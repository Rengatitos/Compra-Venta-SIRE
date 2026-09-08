# NPD del periodo

El trabajo usa el login SOL del scraper regular y las credenciales cifradas de
la empresa. Abre Consulta de NPD (12.4.1.1.6) para establecer las cookies del
modulo ww1.sunat.gob.pe/cl-ti-itnumpagdetr/consultaIndividual.htm.

Completa fec_ini y fec_fin con el primer y ultimo dia del mes y pulsa el boton
consultar(2). Captura una sola consulta consultarPadronIndividual por periodo.
Deduplica los NPD por numero y valida que pertenezcan al RUC solicitado.

Por cada NPD ejecuta secuencialmente POST consultarNPD, GET mostrarDetalleNDP
y GET generarPDFxNPD en la misma sesion. El POST de seleccion puede responder
vacio. Valida numero y RUC en el detalle HTML antes de descargar el PDF.
Estos pasos no se paralelizan porque la seleccion es estado de sesion.

El periodo guarda npds y npds_consultado_en. La tabla permite abrir el detalle,
descargar el PDF obtenido de SUNAT. Si falla el PDF conserva
el detalle y muestra error_pdf. El ZIP incluye exclusivamente los PDFs disponibles. Sin PDFs responde 404.
No se cruza cada comprobante ni se consulta pagos de detracciones. El NPD no
es una constancia de deposito; se conserva su estado, incluido No Vigente.

Las rutas requieren la empresa autenticada. Bajo detracciones se exponen
POST /, GET /disponibilidad, GET /npds, GET /npds/{numero}/pdf y GET /zip. El boton del periodo requiere alguna marca
indDetraccion D en todo el listado de compras. El trabajo comparte cola SOL
por RUC y se encola despues de sincronizar/importar compras.

Validacion local: pruebas del servicio e interfaz y lectura del HTML adjunto
con Chromium. El acceso real completo a SUNAT requiere validacion adicional.
