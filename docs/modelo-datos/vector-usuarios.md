# Modelo de datos — vector_usuarios

Fragmentos de PDFs de referencia subidos por cada empresa, usados como contexto adicional en el análisis con IA. Poblada por [subir_referencia](../../app/api/v1/routes/referencias.py:23), vía [repo_vectores.guardar_chunks](../../app/repositories/vectores.py:37).

| Campo | Descripción |
|---|---|
| `empresa_id` | `_id` de la empresa dueña, como cadena. |
| `texto` | Fragmento del documento. |
| `metadata.documento` | Nombre de archivo original. |
| `metadata.pagina` | Página del PDF. |
| `embedding` | Vector generado con el modelo de embeddings de Gemini. |

Al re-subir un archivo con el mismo nombre, [guardar_chunks](../../app/repositories/vectores.py:37) borra primero todos los chunks anteriores de ese `(empresa_id, documento)` antes de insertar los nuevos — no acumula versiones.

Índice: compuesto sobre `(empresa_id, metadata.documento)`.
