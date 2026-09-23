# Endpoints — Clasificación contable

Asigna a cada comprobante su **cuenta base imponible** (p. ej. `6323094`, auditoría y contable – administración) y su **cuenta total** (`4212`/`1212`) con un RAG híbrido (embeddings E5 + FAISS + BM25) sobre el PCGE, el plan CONTASIS, las notas CIIU y la normativa SUNAT, y tres llamadas a Gemini en Vertex AI: interpretar la operación, su finalidad económica y elegir entre los candidatos que recuperó el RAG. Gemini nunca inventa una cuenta: sólo puede elegir entre las recuperadas.

El motor vive en [app/services/clasificador/](../../app/services/clasificador/) y el puente con los comprobantes en [clasificacion_service.py](../../app/services/clasificacion_service.py). Está **apagado por defecto** (`CLASIFICADOR_HABILITADO=false`); apagado, estos endpoints responden `503` salvo el de estado.

## Qué recibe el clasificador

Hechos, no una preclasificación: los ítems del detalle SUNAT (o la glosa si no hay ítems), los importes, el tipo de comprobante, la contraparte y las actividades económicas (CIIU) y comprobantes autorizados de la empresa y de la contraparte.

Las actividades salen de la **ficha RUC** de la Consulta RUC pública de SUNAT ([ficha_ruc.py](../../app/services/sunat/ficha_ruc.py): Playwright escribe el RUC en el formulario, pulsa «Buscar» y se lee la ficha):

- **Empresa**: se guardan en ella con `POST /empresas/{ruc}/ficha-ruc` (abajo). Si una empresa aún no tiene, la primera clasificación las consulta sola; si SUNAT falla, se usa el CIIU principal de su token. También se pueden editar a mano con `PUT /api/v1/empresas/{ruc}` (ver [empresas](empresas.md)).
- **Contraparte**: si está registrada como empresa se usan las suyas; si no, su ficha, que queda en caché en la colección `fichas_ruc` durante `FICHA_RUC_VIGENCIA_DIAS` (90). El job consulta de una vez las que faltan (`CLASIFICADOR_CONSULTAR_CONTRAPARTES`), con un solo navegador: unos 2–3 s por RUC nuevo.

Un comprobante sin ítems, glosa ni leyenda no se clasifica: no hay operación que interpretar. El job solo toma los que están **«Con glosa»** (misma regla que la columna «Estado glosa»).

**Actividad principal para clasificar.** La ficha de SUNAT no siempre describe el negocio real (un restaurante registrado como venta de electrodomésticos). En Ajustes se agregan actividades del catálogo CIIU Rev. 4 (`GET /api/v1/ciiu?q=`, 418 clases sacadas del PDF del INEI), se quitan las que sobran y se elige cuál manda (`ciiu_principal_clasificacion`, vía `PUT /empresas/{ruc}`). Esa llega al clasificador como PRINCIPAL y las demás como contexto. Volver a consultar SUNAT conserva las agregadas a mano (`origen: "manual"`).

## Candidatos de cuenta

A Gemini le llegan hasta **5 candidatos de cuenta base**, y solo puede elegir entre ellos. Salen de dos búsquedas que se unen:

- La búsqueda semántica del RAG (familia de cuentas y sus divisionarias).
- Una **búsqueda directa en el plan CONTASIS** ([catalogo.py](../../app/services/clasificador/catalogo.py)): las divisionarias cuyo nombre comparte palabras con lo que es la operación, con raíces para que singular y plural casen («combustible» → 603202521 SUMINISTROS COMBUSTIBLES). Antes la cuenta correcta dependía de cómo redactara la IA su interpretación, y a veces no llegaba.

Filtros: solo **cuentas imputables** (divisionarias sin subcuentas; nada de padres como 603 ni códigos sacados del texto del PCGE) y del **elemento que corresponde**: 60–68 en compras (33/34 solo si la finalidad es un activo fijo), 70–77 en ventas.

## Motivo

Cada clasificación guarda su motivo completo: el camino de la cuenta base y de la total en el plan de cuentas (maestro de la empresa o, si no lo cargó, plan CONTASIS) y el porqué de la IA sin el rastro técnico del RAG. Si se reutilizó, lo dice. Las partes se guardan también por separado (`jerarquia_base`, `jerarquia_total`, `motivo_ia`, `reutilizado`) y el texto íntegro de la IA en `razon_ia`. `scripts/recomponer_motivos.py` pasa al formato actual las clasificaciones antiguas.

## Clasificaciones frecuentes

Cada glosa que pasa por la IA queda en la colección `clasificaciones_frecuentes` (por empresa y libro) con la cuenta que se le dio. Si llega otro comprobante con una glosa **equivalente** se reutiliza esa clasificación sin consultar a la IA: se comparan las palabras significativas sin orden, tildes, palabras vacías, meses ni años (Jaccard ≥ `CLASIFICADOR_SIMILITUD_MINIMA`, 0,8), así que «SACOS DE PAPA DE PRIMERA / SACOS DE ZANAHORIA DE PRIMERA» y «SACOS DE PAPA / SACOS DE ZANAHORIA PRIMERA» son la misma ([glosa_similar.py](../../app/domain/glosa_similar.py)).

Solo se reutilizan las **confiables**: las que la IA clasificó sin pedir revisión y las que un usuario corrigió o confirmó. Las dudosas quedan listadas para corregirlas.

**Si la IA no da cuenta para una glosa**, el siguiente comprobante con la misma glosa vuelve a la IA, hasta `CLASIFICADOR_INTENTOS_POR_GLOSA` (3) por trabajo; pasado el tope, el resto queda en revisión sin gastar más consultas. **En cuanto un intento acierta** (o un usuario corrige la clasificación), la frecuente se actualiza y todos los comprobantes con glosa equivalente que estaban en «Requiere revisión», de cualquier periodo, reciben esa cuenta con su motivo. El resultado del job lo cuenta en `propagados`. Una respuesta dudosa de la IA nunca reemplaza a una clasificación confiable o corregida.

- `GET /api/v1/empresas/{ruc}/clasificaciones-frecuentes?libro=` — la lista, de más a menos reutilizada.
- `PATCH …/clasificaciones-frecuentes/{id}` — corrige o confirma la cuenta base (y la total). Pasa a confiable y **se aplica a todos los comprobantes que la usaban** (`clasificacion_contable.memoria_id`).
- `DELETE …/clasificaciones-frecuentes/{id}` — deja de reutilizarse; los comprobantes conservan su cuenta.

En el panel: sección **Clasificaciones** del menú. En la ficha de un comprobante, «Clasificar» reutiliza una frecuente si la hay y «Volver a clasificar con IA» consulta siempre a la IA. Para registrar las clasificaciones hechas antes de existir esta memoria: `scripts/poblar_clasificaciones_frecuentes.py --aplicar`.

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
