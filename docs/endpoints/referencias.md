# Endpoints — Referencias (RAG por empresa)

Todos bajo `/api/v1/empresas/{ruc}/referencias`.

## `GET /api/v1/empresas/{ruc}/referencias`

[listar_referencias](../../app/api/v1/routes/referencias.py:18). Lista los nombres de archivo de los PDFs indexados para esa empresa.

## `POST /api/v1/empresas/{ruc}/referencias`

[subir_referencia](../../app/api/v1/routes/referencias.py:23). Sube un PDF (multipart), lo trocea en chunks por página ([extraer_chunks_pdf](../../app/services/analisis_ia.py:36)), genera un embedding por chunk con Gemini y los guarda en `vector_usuarios`. Si el PDF no tiene texto extraíble, responde `estado: advertencia` sin error. `400` si el archivo no es PDF.

## `DELETE /api/v1/empresas/{ruc}/referencias/{filename}`

[eliminar_referencia](../../app/api/v1/routes/referencias.py:64). Borra todos los chunks de ese documento. `404` si el nombre no existe.

## `GET /api/v1/empresas/{ruc}/referencias/datos`

[obtener_datos_vectoriales](../../app/api/v1/routes/referencias.py:75). Devuelve el texto y los metadatos (sin el embedding) de todos los chunks indexados de la empresa — pensado para depuración, no para consumo normal.

## `GET /api/v1/empresas/{ruc}/referencias/temas-base`

[obtener_temas_base](../../app/api/v1/routes/referencias.py:81). Lista los documentos presentes en el vector **global** (compartido entre todas las empresas, cargado en memoria al arrancar — ver [ciclo de vida](../arquitectura/ciclo-de-vida.md)), no en el de la empresa. Si el vector global está vacío, devuelve un placeholder fijo.

Ver también [flujo de análisis con IA](../flujo/05-analisis-ia.md), que es donde estos documentos se usan como contexto.
