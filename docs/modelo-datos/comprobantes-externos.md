# Modelo de datos — comprobantes externos y códigos de vinculación

## `comprobantes_externos`

Son los comprobantes que registra Apaclla Bot ([repositorio](../../app/repositories/comprobantes_externos.py)). Viven **aparte** de `comprobantes`, porque no vienen de SUNAT: pueden llegar antes de que exista su periodo, y la sincronización de la propuesta nunca los toca.

### Paso al periodo

Cada comprobante externo pertenece al periodo de su `fecha_operacion`: uno del 28/09/2026 va al `202609`. El servicio es [`integracion_externos`](../../app/services/integracion_externos.py).

1. Si el periodo no existe, el externo se queda `recibido`.
2. Si el periodo existe, se busca en `comprobantes` una fila con la misma identidad: `libro`, `tipo_cp`, `serie` y `numero`, normalizados como en la propuesta SUNAT. El origen no cuenta.
   - Si la fila ya está, no se hace nada: el externo queda `ya_existia` y `comprobante_id` apunta a esa fila.
   - Si no está, se copia como una fila más del periodo con `origen: "externo"` (ver [comprobantes](comprobantes.md)). El externo queda `integrado` y `comprobante_id` apunta a la copia.
3. Un voucher (Yape, Plin, Mercado Pago, Niubiz) no es un comprobante de pago y **no se copia como fila**: es el pago de una boleta o factura. Ver «Vouchers como pagos».

Se intenta en estos momentos:
- al recibirlo del bot;
- al listar Externos (su «refresco»);
- al abrir el listado del periodo;
- al crear el periodo, desde el panel o desde una solicitud masiva.

Cuando la propuesta SUNAT (la API o el ticket RCE) trae después el mismo comprobante:
- la fila SIRE reemplaza a la externa y hereda lo que se trabajó sobre ella: la clasificación contable, la contraparte manual y la glosa, esta última solo si se editó;
- el externo pasa a `ya_existia`.

Al borrar el periodo, sus externos vuelven a `recibido`.

### Vouchers como pagos

Un voucher es la prueba de cómo se pagó o cobró un comprobante, así que apunta al comprobante que paga con `pago_de`, su identidad (`periodo`, `libro`, `tipo_cp`, `serie`, `numero`). La identidad, y no un `_id`, sobrevive a que la fila SUNAT reemplace a la externa, a una resincronización y a borrar y recrear el periodo. El servicio es [`pagos_vouchers`](../../app/services/pagos_vouchers.py).

1. Mientras su periodo no existe, el voucher queda `recibido`. En cuanto existe, queda `integrado`: se ve en el periodo, asociado o no.
2. **La asociación automática** busca en el periodo del voucher **y en el anterior** un comprobante que cumpla todo esto. Un Yape del 2 de octubre suele cobrar una boleta de fines de septiembre; lo contrario, pagar antes de que exista el comprobante, casi no pasa.
   - es del mismo libro;
   - tiene la misma moneda y el mismo total, con la tolerancia de un céntimo;
   - si el voucher trae documento de la contraparte, tiene ese mismo documento;
   - no es una nota de crédito o débito;
   - no está pagado ya por otro voucher.

   Solo asocia si hay **una única** candidata entre los dos periodos, y entonces `asociacion` es `auto`. Si hay varias o ninguna, el voucher queda «sin comprobante». Una en cada mes también es ambigua.
3. **Desde el periodo** se asocia a mano, o se desasocia. En los dos casos `asociacion` es `manual` y la asociación automática ya no lo toca.
4. Se reintenta al abrir el periodo, al integrar externos pendientes y después de cada sincronización de la propuesta, que es cuando llegan boletas y facturas nuevas. En cada caso se reintentan también los vouchers del periodo siguiente, que pueden pagar los comprobantes recién llegados.
5. Si el comprobante asociado ya no está en el periodo, el voucher vuelve a «sin comprobante». Si su asociación era `auto`, se busca otra vez.
6. **El pago se ve en el comprobante, en el periodo de este:** en su listado, en su ficha y en su plantilla. El voucher sigue siendo del periodo de su `fecha_operacion`, y si está sin comprobante sale en el panel y en la hoja de ese periodo. Nunca se asocia a un comprobante de dos meses atrás ni del mes siguiente.
7. La versión anterior copiaba el voucher como fila `tipo_cp "00"`. Esa fila se borra al refrescar el periodo y el voucher queda como pago.

**En la plantilla Contasis** ([consulta y exportación](../flujo/06-consulta-exportacion.md)):
- la fila del comprobante lleva el medio de pago y el número de operación;
- en ventas, la columna «MEDIO DE PAGO» lleva el código de la Tabla 1 de SUNAT (`MEDIO_PAGO_POR_FUENTE` en [comprobante_externo.py](../../app/domain/comprobante_externo.py)): Yape y Plin van con `003`, transferencia de fondos; Mercado Pago y Niubiz con `999`, otros. **Hay que confirmarlo con el contador**;
- los vouchers sin comprobante van a la hoja «Vouchers sin comprobante».

| Campo | Tipo | Notas |
|---|---|---|
| `_id` | ObjectId | Es el `id` que se devuelve al bot |
| `empresa_id` | str | `str(empresas._id)` |
| `id_externo` | str | Id del envío en el bot (ULID); da la idempotencia |
| `libro` | `ventas` \| `compras` | |
| `fuente` | `yape` \| `plin` \| `mercado_pago` \| `niubiz` \| `boleta` \| `factura` \| `otro` | |
| `tipo_evidencia` | `voucher` \| `comprobante` | |
| `tipo_cp`, `serie`, `numero`, `nro_operacion` | str | Un voucher usa `tipo_cp "00"` y `nro_operacion` |
| `fecha_operacion` | datetime (medianoche UTC) | |
| `hora_operacion` | str \| null | |
| `moneda` | `PEN` \| `USD` | |
| `total`, `base_imponible`, `igv` | Decimal128 | |
| `contraparte` | `{tipo_doc_identidad, documento, nombre}` | |
| `descripcion`, `confianza`, `campos_dudosos` | | Lo que extrajo la visión del bot y lo que no tenía claro |
| `imagen` | `{sha256, mime, bytes, archivo}` | `archivo` es el nombre del archivo dentro de `COMPROBANTES_EXTERNOS_DIR/{empresa_id}/`; null si llegó sin foto |
| `dispositivo_id` | str | Dispositivo vinculado que lo mandó |
| `enviado_en`, `creado_en` | datetime | |
| `periodo` | str `YYYYMM` | Sale de `fecha_operacion` |
| `estado` | `recibido` \| `integrado` \| `ya_existia` | Ver «Paso al periodo». Un voucher nunca queda `ya_existia` |
| `comprobante_id` | str \| null | `_id` de la fila de `comprobantes` a la que pasó o que ya lo tenía. Siempre null en un voucher |
| `pago_de` | `{periodo, libro, tipo_cp, serie, numero}` \| null | Solo vouchers: el comprobante que paga, de su periodo o del anterior |
| `asociacion` | `auto` \| `manual` \| null | Solo vouchers: cómo quedó `pago_de`. `manual` también si se desasoció a mano |
| `integrado_en` | datetime \| null | Cuándo dejó de estar `recibido` |

Índices:
- `uniq_externo_id_externo`: único sobre `(empresa_id, id_externo)`.
- `uniq_externo_operacion`: único parcial sobre `(empresa_id, fuente, nro_operacion)`, solo cuando `nro_operacion` no está vacío.
- `uniq_externo_serie_numero`: único parcial sobre `(empresa_id, libro, tipo_cp, serie, numero)`, solo para `tipo_evidencia = "comprobante"`.
- `externos_listado`: `(empresa_id, libro, periodo, creado_en -1)`.
- `externos_pendientes`: `(empresa_id, estado, periodo)`, para los que esperan su periodo.
- `externos_vouchers`: `(empresa_id, periodo, tipo_evidencia)`, para los vouchers de un periodo.
- `externos_vouchers_pago_de`: `(empresa_id, pago_de.periodo)`, parcial sobre `tipo_evidencia = "voucher"`, para los que pagan comprobantes de un periodo.

## `codigos_vinculacion`

Códigos de 6 dígitos para vincular un dispositivo del bot ([repositorio](../../app/repositories/codigos_vinculacion.py)). **Nunca se guarda el código en claro**, solo su sha256.

| Campo | Notas |
|---|---|
| `empresa_id`, `ruc` | |
| `codigo_hash` | sha256 del código |
| `creado_en`, `expira_en` | `expira_en = creado_en + 10 min` |
| `creado_por` | Correo de quien lo generó en el panel |
| `usado_en`, `dispositivo_id` | Se llenan al canjearlo |

Índices:
- `ttl_expira_en`: TTL sobre `expira_en`. Mongo borra solos los vencidos; los canjeados se quedan hasta entonces para poder responder `409` («ya se usó») en vez de `400`.
- `uniq_ruc_codigo`: único sobre `(ruc, codigo_hash)`.

Borrar una empresa elimina sus comprobantes externos, sus códigos y su carpeta de fotos.
