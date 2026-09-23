# Endpoints — Clasificación contable

Asigna a cada comprobante su **cuenta base imponible** (p. ej. `6323094`, auditoría y contable – administración) y su **cuenta total** (`4212`/`1212`) con un RAG híbrido (embeddings E5 + FAISS + BM25) sobre el PCGE, el plan CONTASIS, las notas CIIU y la normativa SUNAT, y tres llamadas a Gemini en Vertex AI: interpretar la operación, su finalidad económica y elegir entre los candidatos que recuperó el RAG. Gemini nunca inventa una cuenta: sólo puede elegir entre las recuperadas.

El motor vive en [app/services/clasificador/](../../app/services/clasificador/) y el puente con los comprobantes en [clasificacion_service.py](../../app/services/clasificacion_service.py). Está **apagado por defecto** (`CLASIFICADOR_HABILITADO=false`); apagado, estos endpoints responden `503` salvo el de estado.

## Qué recibe el clasificador

Hechos, no una preclasificación: los ítems del detalle SUNAT (o la glosa si no hay ítems), los importes, el tipo de comprobante, la contraparte y las actividades económicas (CIIU) y comprobantes autorizados de la empresa y de la contraparte.

Las actividades salen de la **ficha RUC** de la Consulta RUC pública de SUNAT ([ficha_ruc.py](../../app/services/sunat/ficha_ruc.py): Playwright escribe el RUC en el formulario, pulsa «Buscar» y se lee la ficha):

- **Empresa**: se guardan en ella con `POST /empresas/{ruc}/ficha-ruc` (abajo). Si una empresa aún no tiene, la primera clasificación las consulta sola; si SUNAT falla, se usa el CIIU principal de su token. También se pueden editar a mano con `PUT /api/v1/empresas/{ruc}` (ver [empresas](empresas.md)).
- **Contraparte**: si está registrada como empresa se usan las suyas; si no, su ficha, que queda en caché en la colección `fichas_ruc` durante `FICHA_RUC_VIGENCIA_DIAS` (90). El job consulta de una vez las que faltan (`CLASIFICADOR_CONSULTAR_CONTRAPARTES`), con un solo navegador: unos 2–3 s por RUC nuevo.

Un comprobante sin ítems, glosa ni leyenda no se clasifica: no hay operación que interpretar.

## Qué guarda

El resultado se guarda en el comprobante, en `clasificacion_contable`, y sale en la respuesta de `GET .../comprobantes`: `cuenta_base`, `cuenta_total`, `clasificacion`, `subtipo`, `condicion_igv`, `confianza`, `requiere_revision`, `razon`, `modelo` y `clasificado_en`.

`requiere_revision` es `true` cuando la confianza no llega a `REVIEW_CONFIDENCE_THRESHOLD` (0,60 por defecto), falta alguna de las dos cuentas, la finalidad económica quedó indeterminada o había candidatos ambiguos (por ejemplo, la misma cuenta para administración y para ventas).

**En el panel**, la tabla de comprobantes tiene la columna «Cuenta» (con la marca «Revisar»), la ficha de cada comprobante una sección «Clasificación contable» con su botón, y la página del periodo el panel para clasificar todo el libro.

**En el Excel de Contasis** —el del botón Excel y el del reporte asociado, que usa la misma plantilla— la cuenta base (columna AF en compras, AB en ventas) sólo se escribe si `requiere_revision` es `false`: una celda vacía obliga al contador a mirarla, una cuenta dudosa se importaría sin que nadie la revise. La cuenta total sigue fija en `4212`/`1212` ([plantilla_excel.py](../../app/services/plantilla_excel.py)). El Excel y el PDF de un comprobante suelto muestran la clasificación completa, requiera revisión o no.

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/libros/{libro}/clasificacion`

[iniciar_clasificacion](../../app/api/v1/routes/clasificacion.py). Job asíncrono que clasifica los comprobantes del libro que aún no tienen clasificación, hasta `CLASIFICADOR_MAX_COMPROBANTES` (200) por vuelta. Con `?reclasificar=true` vuelve a clasificar también los ya clasificados. Límite: 5/minuto. `409` si ya hay una clasificación del mismo periodo y libro en marcha.

Responde `202` con un `job_id`; el avance y el resultado se consultan en [GET /api/v1/jobs/{job_id}](jobs.md). El resultado:

```json
{
  "clasificados": 48,
  "requieren_revision": 11,
  "sin_descripcion": 3,
  "errores": 1,
  "pendientes_restantes": 1,
  "detalle_errores": [{"serie_numero": "F001-22", "error": "GEMINI_API_ERROR: ..."}]
}
```

Un error de Gemini en un comprobante no detiene el lote: ese comprobante queda sin clasificar y entra en la siguiente vuelta. Todas las clasificaciones comparten una cola, porque el motor es uno por proceso.

## `POST /api/v1/empresas/{ruc}/periodos/{periodo}/comprobantes/{serie_numero}/clasificacion`

[clasificar_comprobante](../../app/api/v1/routes/comprobantes.py). Clasifica un comprobante en el acto (unos segundos) y guarda el resultado, reemplazando el anterior. `?libro=` desambigua si la serie-número existe en ambos libros. `422` si no tiene nada que clasificar, `502` si falla Vertex AI.

## `POST /api/v1/empresas/{ruc}/ficha-ruc` — obtener CIIU de la empresa

[obtener_ciiu_empresa](../../app/api/v1/routes/empresas.py). Consulta la ficha RUC de la empresa en SUNAT y guarda en ella `actividades_economicas` (reemplazando las que hubiera) y `ficha_ruc` completa. Devuelve la empresa. `404` si SUNAT no tiene ese RUC, `502` si la consulta falla. Límite: 10/minuto. En el panel: Ajustes → «Obtener CIIU desde SUNAT».

Ejemplo de lo que queda guardado:

```json
"actividades_economicas": [
  {"tipo": "PRINCIPAL", "ciiu": "4759", "descripcion": "VENTA AL POR MENOR DE APARATOS ELÉCTRICOS DE USO DOMÉSTICO, ..."},
  {"tipo": "SECUNDARIA", "ciiu": "5320", "descripcion": "ACTIVIDADES DE MENSAJERÍA"}
]
```

## `GET /api/v1/consulta-ruc/{ruc}`

[consultar_ruc](../../app/api/v1/routes/consulta_ruc.py). Ficha RUC de cualquier contribuyente (proveedor, cliente), registrado o no: razón social, estado, condición, actividades CIIU, comprobantes autorizados, sistema de emisión electrónica. Sale de la caché si está vigente; `?refrescar=true` fuerza la consulta a SUNAT. Requiere sesión. Límite: 20/minuto.

## `GET /api/v1/clasificador/estado`

Estado del motor: `deshabilitado`, `sin_iniciar`, `cargando`, `listo` o `error` (con el motivo), el modelo de Gemini y cuántos documentos y fragmentos hay indexados. Requiere sesión.

## `POST /api/v1/clasificador/reindexar`

Recalcula los embeddings de los documentos de conocimiento nuevos o modificados en `app/resources/clasificador/conocimiento/` (con `?forzar=true`, de todos). Límite: 2/minuto.

## Puesta en marcha

1. `CLASIFICADOR_HABILITADO=true` en el `.env`, más `GOOGLE_APPLICATION_CREDENTIALS` (ruta al JSON de una cuenta de servicio con acceso a Vertex AI; nunca al repositorio), `VERTEX_PROJECT` y `VERTEX_LOCATION` (ver [.env.example](../../.env.example)).
2. Al arrancar, la API carga el motor en un hilo sin retrasar el arranque. La primera vez descarga el modelo de embeddings (~470 MB) e indexa el conocimiento en `data/clasificador/` (en Docker, el volumen de `/app/data`), lo que tarda varios minutos; después se reutiliza.
3. Suma alrededor de 1 GB de RAM al proceso.
4. Para traer las actividades de los antiguos `company_heads/*.json`: `uv run python scripts/migrar_actividades_empresas.py --aplicar`.
