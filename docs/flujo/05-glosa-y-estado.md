# Flujo — Glosa y estado por tipo de comprobante

La glosa es el texto que el contador lee en la columna GLOSA del registro Contasis. Sale del detalle que publica SUNAT, así que depende de que el portal tenga el comprobante. Este documento explica de dónde sale, qué estado se le asigna a cada comprobante y qué tipos no se consultan nunca.

## De dónde sale la glosa

`obtener_glosa` en [glosa.py](../../app/services/glosa.py) aplica tres fuentes, en este orden, y se queda con la primera que dé texto:

1. **Glosa manual.** Lo que el usuario escribió con `PATCH …/comprobantes/{serie_numero}` (campo `descripcion`). Gana siempre, aunque esté vacía: borrarla a mano es una decisión.
2. **Descripciones del detalle.** Las descripciones únicas de `detalle_sunat`, unidas con ` / ` y recortadas a 500 caracteres.
3. **Leyenda del comprobante.** Cuando los ítems no describen nada, las líneas del recuadro «LEYENDA» del popup de SOL (`leyenda_sunat`). Muchas facturas recibidas de bancos traen el ítem `CONCEPTO DE PAGO:COMISION` vacío de descripción y la leyenda `TARJETA DE DEBITO`. Se descartan las líneas que no describen: el importe en letras (`SON DIEZ CON 00/100 SOLES`), fechas, números de tarjeta enmascarados y siglas de tres letras o menos (`TD`, `SAT`).

La ruta SEE-SOL (series `E…`) no tiene recuadro de leyenda: su impresión ya trae la descripción en la tabla de ítems.

## Qué publica SUNAT de cada tipo

El portal SOL no tiene todos los comprobantes. El alcance acordado con el cliente el 12 de septiembre de 2026 clasificó los 53 tipos de la Tabla 3 del anexo del SIRE, y el catálogo vive en [catalogos.py](../../app/domain/catalogos.py):

| Grupo | Constante | Tipos | Qué pasa con ellos |
|---|---|---|---|
| Con detalle en SUNAT | `TIPOS_CON_DETALLE_SUNAT` | 01, 03, 07 (verificados) y 08, 13, 14, 18, 19, 23, 29, 34, 35, 36, 42, 64, 87, 88 (el scraper los trata igual, faltan casos reales) | Se consultan en SOL; la glosa sale de sus ítems |
| Sin detalle en SUNAT | `TIPOS_SIN_DETALLE_SUNAT` | 00, 04, 05, 06, 09, 10, 11, 12, 15, 16, 17, 21, 22, 24, 25, 26, 27, 28, 30, 31, 32, 37, 43, 44, 45, 48, 49, 53, 55, 56, 89, 91, 96, 97, 98 | No se consultan; se entregan con los datos del SIRE y sin glosa |
| En evaluación | `TIPOS_EN_EVALUACION` | 02 | SUNAT lo publica por otro módulo (ver abajo) |

Dos reclasificaciones respecto al alcance original, ambas del 18 de septiembre de 2026:

- **30** (documentos de los adquirentes de tarjetas: Niubiz, Izipay…) estaba «con glosa». Los dos casos reales disponibles (`FD01-862873` y `FD01-236512`, RUC 20603391692) no aparecen en ninguna bandeja del portal: la búsqueda en «FE Recibidas» agota el plazo sin resultado. Son documentos autorizados, no comprobantes electrónicos, y pasan a sin detalle.
- **Los doce tipos en evaluación** quedaron resueltos. Once no tienen contenido publicado por SUNAT y pasan a sin detalle: guías de remisión (09, 31), formularios (10 arrendamiento, 22 operaciones no habituales), atribución de IGV (25), agua con fines agrarios (26), declaración courier (53), documentos de no domiciliados (91, 97, 98) y exceso de crédito fiscal (96). El **02** (recibo por honorarios electrónico) sí tiene contenido, pero en el módulo «Recibos por honorarios → consulta de recibos recibidos» de SOL, que el scraper no recorre: queda en evaluación hasta que se decida construir esa ruta.

### Excepciones por libro

`SIN_DETALLE_POR_LIBRO` recoge tipos consultables en general que no lo son en un registro concreto. Hoy sólo hay una: **boletas (03) en compras**. El combo «Tipo de consulta» del portal tiene exactamente nueve bandejas —FE, NC y ND Emitidas y Recibidas, y BVE, NC-BVE y ND-BVE Emitidas - OSE— y ninguna de boletas recibidas (`scripts/listar_bandejas_sol.py` las enumera). Una boleta `B001` recibida no se puede consultar; una `EB01` recibida sí, porque va por SEE-SOL. Por eso la excepción respeta la serie: `sin_detalle_en_sunat(tipo, libro, serie)`.

## El estado de la glosa

Cada comprobante lleva `estado_glosa` (`estado_glosa` en [glosa.py](../../app/services/glosa.py)), que el listado muestra como insignia y el Excel en la columna «Estado glosa»:

| Estado | Cuándo | Observación que lo acompaña |
|---|---|---|
| `con_glosa` | Hay glosa, venga de donde venga | — |
| `sin_glosa` | El tipo no tiene detalle en SUNAT, o es consultable y ya se consultó sin resultado | «SUNAT no publica el detalle de este tipo de comprobante» o «No se pudo obtener glosa» |
| `en_evaluacion` | El tipo está en evaluación, o el código no está en el catálogo | «Tipo de comprobante en evaluación» |
| `pendiente` | Tipo consultable que todavía no pasó por el portal | — |

`glosa_consultada` es la marca que deja el job de detalle en cada comprobante que efectivamente buscó (encontrado o no). Es lo que separa «sin glosa» de «pendiente». Un comprobante sin tipo se trata como consultable.

El botón «Descargar reporte y asociado» sólo espera a los `pendiente`: los `sin_glosa` y `en_evaluacion` son definitivos y no bloquean el reporte.

## Lo que el job de detalle no consulta

Los filtros de pendientes del repositorio ([comprobantes.py](../../app/repositories/comprobantes.py), `_excluir_tipos_sin_detalle`) dejan fuera los tipos sin detalle y las boletas recibidas que no son SEE-SOL. Buscarlos costaba un timeout por comprobante para terminar en «no encontrado». El job informa cuántos dejó fuera en `omitidos_sin_detalle` y en su primer mensaje de progreso.

## Cómo se evalúa un tipo nuevo

Cuando el cliente entregue un RUC y periodo con alguno de los 14 tipos que requieren casos:

1. Alta de la empresa, sincronizar el periodo y lanzar la extracción de detalle.
2. `uv run python scripts/informe_tipos.py --ruc <ruc> --periodo <periodo>` genera el informe por tipo con la última línea del log por comprobante.
3. Si el portal devolvió ítems, el tipo se queda en `TIPOS_CON_DETALLE_SUNAT`; si ninguna bandeja lo lista, pasa a `TIPOS_SIN_DETALLE_SUNAT` con el caso anotado en el comentario del catálogo. `tests/domain/test_catalogos.py` guarda los tamaños de cada grupo.
