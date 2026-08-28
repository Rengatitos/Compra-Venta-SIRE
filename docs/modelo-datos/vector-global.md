# Modelo de datos — vector_global

Base de conocimiento normativa (Plan Contable General Empresarial) compartida por todas las empresas, cargada en memoria al arrancar el servidor mediante [cargar_vector](../../app/services/analisis_ia.py:28) (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)). Esta colección no se puebla desde ningún endpoint visible en el código — se asume gestionada por un proceso o script externo, o por una carga manual directa a Mongo.

| Campo | Descripción |
|---|---|
| `texto` | Fragmento de texto normativo. |
| `metadata.documento` | Nombre del documento fuente. |
| `metadata.pagina` | Página del PDF de origen, cuando aplica. |
| `embedding` | Vector de números de punto flotante, generado con el modelo de embeddings de Gemini. |

Índice: sobre `metadata.documento`.
