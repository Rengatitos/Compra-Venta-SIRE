# Modelo de datos — vector_global

Base de conocimiento normativa (Plan Contable General Empresarial) compartida por todas las empresas, cargada en memoria al arrancar el servidor mediante [cargar_vector](../../app/services/analisis_ia.py:28) (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)). Ningún endpoint la puebla: la carga es fuera de línea, con [scripts/indexar_vector_global.py](../../scripts/indexar_vector_global.py), que lee los PDFs de `source/normativa/`, los trocea, pide los embeddings a Gemini e inserta. Es idempotente y reanudable, y también importa un embedding ya calculado con `--importar-json`.

| Campo | Descripción |
|---|---|
| `texto` | Fragmento de texto normativo. |
| `metadata.documento` | Nombre del documento fuente. |
| `metadata.pagina` | Página del PDF de origen, cuando aplica. |
| `metadata.chunk` | `"<página>-<orden>"`. Clave de reanudación del script; el backend no la lee. |
| `embedding` | Vector de números de punto flotante, generado con el modelo de embeddings de Gemini. |

Índice: sobre `metadata.documento`.

## Qué conviene indexar aquí

El embedding se genera con `models/gemini-embedding-001` **sin `config`**, exactamente igual que la consulta en [buscar_contexto](../../app/services/analisis_ia.py:111). Pasar un `task_type` o un `output_dimensionality` distinto rompería la comparabilidad de los vectores: el producto punto fallaría, la excepción se tragaría en el `except` de esa función y el análisis se quedaría sin contexto normativo sin ningún error visible.

`buscar_contexto` tiene `top_k` fijo en 20 y no reordena por fuente, así que **la composición de la colección decide qué ve el modelo**. El texto de consulta que arma [texto_para_ia](../../app/services/comprobante_service.py:64) es una cabecera de comprobante (tipo, serie-número, RUC, montos, IGV), de modo que cualquier norma que describa comprobantes —el Reglamento de Comprobantes de Pago, la Ley del IGV— gana por coseno a las cuentas del PCGE y lo expulsa del top-20 aunque no responda ninguno de los campos que pide el prompt. Medido sobre casos reales, el PCGE cae de 14-19 de 20 a 0-7 de 20 al añadir esos documentos.

Por eso aquí va sólo la base contable (PCGE y renta neta). La normativa de comprobantes y de IGV se indexa en [vector_usuarios](vector-usuarios.md), que en `buscar_contexto` se puntúa aparte y tiene su propio top-20.
