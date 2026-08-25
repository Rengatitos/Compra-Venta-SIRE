# Modelo de datos — vector_users

Fragmentos de PDFs de referencia subidos por cada usuario (ver [endpoints — References](../endpoints/references.md)), usados como contexto RAG adicional específico de esa empresa en el [flujo de análisis con IA](../flujo/05-analisis-ia.md).

| Campo | Descripción |
|---|---|
| usuario | Dueño del documento. |
| texto, metadata (nombre de documento y página), embedding | Misma estructura que vector_global. |

Índice: compuesto por usuario y nombre de documento dentro de metadata. Al volver a subir un archivo con el mismo nombre para el mismo usuario, [guardar_chunks_usuario](../../app/services/vector_store.py:17) borra primero los fragmentos previos de ese documento — es un reemplazo completo, no una fusión con lo ya existente.
