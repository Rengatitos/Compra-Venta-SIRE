# Endpoints — References

Prefijo `/references`, montado en [main.py](../../app/main.py:127). Router en [references.py](../../app/api/routes/references.py). Estos endpoints implementan el RAG por usuario: PDFs que cada empresa sube como contexto adicional para el análisis con IA.

| Método | Path completo | Función | Auth |
|---|---|---|---|
| GET | `/references/files/{user_id}` | [listar_archivos](../../app/api/routes/references.py:17) | require_same_user |
| POST | `/references/upload/{user_id}` | [subir_referencia](../../app/api/routes/references.py:24) | require_same_user |
| DELETE | `/references/files/{user_id}/{filename}` | [eliminar_referencia](../../app/api/routes/references.py:75) | require_same_user |
| GET | `/references/data/{user_id}` | [obtener_datos_vectoriales](../../app/api/routes/references.py:88) | require_same_user |
| GET | `/references/base-topics` | [obtener_temas_base](../../app/api/routes/references.py:95) | verify_user |

**listar_archivos** devuelve los nombres de los documentos PDF ya indexados para el usuario.

**subir_referencia** sube un PDF, extrae su texto, lo divide en fragmentos, genera los embeddings correspondientes y los persiste en la colección de embeddings por usuario. Ver [modelo de datos — vector-users](../modelo-datos/vector-users.md).

**eliminar_referencia** borra todos los fragmentos de un documento para ese usuario; devuelve un error si no existía ninguno.

**obtener_datos_vectoriales** devuelve los fragmentos de texto indexados del usuario, sin incluir el vector de embedding.

**obtener_temas_base** lista los documentos distintos presentes en la base normativa global, cargada en memoria durante el arranque del servidor (ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)).
