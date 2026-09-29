# API de Sire para análisis de datos

Cómo extraer los datos de Sire —empresas, periodos, comprobantes de compras y
ventas, su clasificación contable, comprobantes recibidos por el bot y los
agregados del panel— para cargarlos en un almacén de datos y transformarlos allí.

## 1. Conexión
* Correo: vasquezciro654@gmail.com
* Contraseña: V5eL972g_bBERmFhJMyyrDq4903PiftW

CURL CONEXIÓN:

```bash
curl -s -X POST "https://apaclla-web.p7slsc.easypanel.host/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email": "vasquezciro654@gmail.com", "password": "V5eL972g_bBERmFhJMyyrDq4903PiftW"}' 
```

| | |
|---|---|
| **URL base** | `https://apaclla-web.p7slsc.easypanel.host/api/v1` |
| Formato | JSON (UTF-8). Las exportaciones devuelven Excel, PDF o ZIP. |
| Credenciales | Un **correo** y una **contraseña** que te entrega Apaclla. Dan acceso a toda la API. |
| Autenticación | `Authorization: Bearer <token>` en todas las rutas salvo el login |
| Vigencia del token | **5 horas**. Al vencer, la API responde `401 Token expirado`: se pide otro igual. |

Hay una colección de Postman lista para importar:
[`sire-api.postman_collection.json`](sire-api.postman_collection.json). Solo hay que
llenar las variables `email` y `password`; el token se pide y se renueva solo.

## 2. Obtener el token

Una sola llamada con el correo y la contraseña:

```bash
export SIRE="https://apaclla-web.p7slsc.easypanel.host/api/v1"

export TOKEN=$(curl -s -X POST "$SIRE/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email": "<correo>", "password": "<contraseña>"}' \
  | jq -r .access_token)
```

Respuesta:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 18000,
  "usuario": {"email": "<correo>", "nombre": null, "foto": null, "rol": "admin"}
}
```

- `expires_in` son los segundos de vigencia (18000 = 5 horas). Pasado ese tiempo
  se vuelve a llamar a `/auth/token`.
- Se admiten **5 intentos por minuto**; más allá, `429`.
- Guarda la contraseña como variable de entorno o en un gestor de secretos, nunca
  en el código.

Comprobar que el token funciona:

```bash
curl -s "$SIRE/auth/yo" -H "Authorization: Bearer $TOKEN"
# {"email":"<correo>","nombre":null,"foto":null,"rol":"admin"}
```

Variables que usan los ejemplos siguientes:

```bash
export RUC="20603391692"      # 11 dígitos
export PERIODO="202609"       # YYYYMM
```

## 3. Convenciones

- **`periodo`**: `YYYYMM` (septiembre de 2026 = `202609`).
- **`libro`**: `ventas` o `compras`.
- **`ruc`**: 11 dígitos, sin espacios.
- **Importes**: números en la moneda del comprobante (`moneda`, con `tipo_cambio` si es USD).
- **Paginación**: `limit` y `skip`. Se pide página a página hasta que llegue
  una lista más corta que `limit`.
- **Límites**: el login admite 5 peticiones/min; las de lectura no tienen un
  límite fijo, pero conviene no pasar de unas pocas por segundo: la API corre en
  una VM de 4 GB con un solo proceso.

Encabezado común para no repetirlo:

```bash
H=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/json")
```

## 4. Extracción: dimensiones

### Empresas

```bash
curl -s "${H[@]}" "$SIRE/empresas"
```

Cada empresa trae `ruc`, `nombre`, `usuario` (SOL), `fecha_creacion`, `rubro`,
`ciiu`, `actividades_economicas`, `ciiu_principal_clasificacion` y `ficha_ruc`
(razón social, dirección, estado…). No incluye contraseñas ni credenciales de SUNAT.

Resumen de todas las empresas (procesos por estado en los últimos días):

```bash
curl -s "${H[@]}" "$SIRE/empresas/resumen"
```

### Periodos

Periodos registrados de una empresa, con su estado:

```bash
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos"
# [{"periodo":"202609","estado":"..."}, ...]
```

Periodos que tienen datos, para una o varias empresas (`rucs` separados por coma;
sin `rucs`, todas):

```bash
curl -s "${H[@]}" "$SIRE/analytics/periodos?rucs=20603391692,10209911031"
```

### Plan de cuentas de la empresa

```bash
curl -s "${H[@]}" "$SIRE/empresas/$RUC/plan-cuentas?limit=3000&skip=0"
# busqueda=<texto> filtra por código o descripción
```

### Clasificaciones frecuentes (memoria del clasificador)

Glosas ya clasificadas y la cuenta que se les asignó; útil para validar o
entrenar reglas propias:

```bash
curl -s "${H[@]}" "$SIRE/empresas/$RUC/clasificaciones-frecuentes?libro=compras"
```

Campos: `glosa`, `cuenta_base`, `cuenta_total`, `clasificacion`, `subtipo`,
`confianza`, `confiable`, `origen` (`ia` o `usuario`), `usos`, `actualizado_en`.

### Catálogo CIIU

```bash
curl -s "${H[@]}" "$SIRE/ciiu?q=restaurante"
```

## 5. Extracción: hechos

### Comprobantes de un periodo (tabla principal)

```bash
curl -s "${H[@]}" \
  "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes?libro=compras&limit=500&skip=0"
```

Sin `libro` devuelve ambos libros. Campos de cada comprobante:

| Grupo | Campos |
|---|---|
| Identificación | `serie_numero`, `libro`, `origen`, `tipo_cp`, `tipo_cp_descripcion`, `serie`, `numero` |
| Contraparte | `tipo_doc_identidad`, `documento_contraparte`, `razon_social` |
| Fechas y moneda | `fecha_emision`, `fecha_vencimiento`, `moneda`, `tipo_cambio`, `porcentaje_igv` |
| Importes | `base_imponible`, `igv`, `base_imponible_dg`, `igv_dg`, `base_imponible_dgng`, `igv_dgng`, `base_imponible_dng`, `igv_dng`, `exonerado`, `inafecto`, `no_gravado`, `isc`, `icbper`, `otros_tributos`, `total` |
| Detalle de SUNAT | `glosa`, `estado_glosa`, `leyenda_sunat`, `detalle_sunat`, `observacion`, `analisis`, `estado_procesamiento`, `pdf_sunat` |
| Detracciones | `detraccion`, `detracciones`, `detracciones_consultado_en` |
| Relacionados | `documentos_modificados` (notas de crédito o débito) |
| **Clasificación contable** | `clasificacion_contable` (ver abajo) |

`clasificacion_contable` trae: `cuenta_base`, `cuenta_total`, `clasificacion`,
`subtipo`, `condicion_igv`, `centro_costos`, `confianza`, `confianza_rag`,
`requiere_revision`, `razon`, `motivo_ia`, `jerarquia_base`, `jerarquia_total`,
`modelo`, `clasificado_en`, `origen`, `reutilizado`. Es `null` si el comprobante
aún no se clasificó.

Un comprobante concreto:

```bash
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/F001-66929?libro=compras"
```

### Comprobantes recibidos por Apaclla Bot (fotos de vouchers, boletas y facturas)

```bash
curl -s "${H[@]}" \
  "$SIRE/empresas/$RUC/comprobantes-externos?periodo=$PERIODO&libro=ventas&limit=100&skip=0"
# fuente=yape|plin|mercado_pago|niubiz|boleta|factura|otro ; limit máximo 100
```

Detalle y foto de uno:

```bash
curl -s "${H[@]}" "$SIRE/empresas/$RUC/comprobantes-externos/<id>"
curl -s -H "Authorization: Bearer $TOKEN" -o foto.jpg \
  "$SIRE/empresas/$RUC/comprobantes-externos/<id>/imagen"
```

## 6. Agregados listos (los del dashboard)

Todos aceptan `rucs` (lista separada por coma; sin él, todas las empresas) y
`libro` (por defecto `compras`).

```bash
# Totales del periodo
curl -s "${H[@]}" "$SIRE/analytics/summary?periodo=$PERIODO&libro=compras&rucs=$RUC"

# Contrapartes con mayor monto
curl -s "${H[@]}" "$SIRE/analytics/top-contrapartes?periodo=$PERIODO&libro=ventas&limit=20"

# Comprobantes por día
curl -s "${H[@]}" "$SIRE/analytics/comprobantes-por-dia?periodo=$PERIODO&libro=compras"

# Todo lo anterior en una sola llamada
curl -s "${H[@]}" "$SIRE/analytics/dashboard-data?periodo=$PERIODO&libro=compras&rucs=$RUC"
```

Para un almacén de datos conviene calcular estos agregados desde los
comprobantes (sección 5). Estas rutas sirven para cuadrar los resultados con lo
que muestra el panel.

## 7. Calidad y conciliación

```bash
# Comprobantes a los que les falta el detalle de SUNAT
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/incompletos?libro=compras"

# Comprobantes anulados en SUNAT
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/anulados-sunat?libro=ventas"

# Cobertura: cuántos tienen detalle y PDF de SUNAT
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/cobertura-sunat?libro=compras"

# Compras frente al resumen oficial del RCE en el SIRE
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/conciliacion-rce"

# Tabla comparativa del auditor (glosas y fuentes), hasta 5000 filas
curl -s "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/libros/compras/auditoria/reporte?limit=5000"
```

## 8. Metadatos operativos (linaje de la carga)

Qué procesos corrieron, cuándo y con qué resultado, para saber si los datos de
un periodo están completos antes de extraerlos:

```bash
# Trabajos (limit máximo 200)
curl -s "${H[@]}" "$SIRE/jobs?ruc=$RUC&periodo=$PERIODO&estado=completado&limit=200"
#   tipo:   sincronizacion_sire | extraccion_detalles | descarga_pdfs | detracciones
#           clasificacion_cuentas | empaquetado | envio_correo | alta_empresa | credenciales_sunat
#   estado: pendiente | en_progreso | completado | fallido

curl -s "${H[@]}" "$SIRE/jobs/<job_id>"

# Solicitudes de procesamiento masivo y su avance por empresa y periodo
curl -s "${H[@]}" "$SIRE/solicitudes"
curl -s "${H[@]}" "$SIRE/solicitudes/<solicitud_id>"
```

## 9. Archivos

```bash
# Excel del libro, con el formato oficial (formato=excel exige libro)
curl -s -H "Authorization: Bearer $TOKEN" -o compras_$RUC_$PERIODO.xlsx \
  "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes/export?formato=excel&libro=compras"

# PDFs de SUNAT ya descargados, en un ZIP
curl -s -H "Authorization: Bearer $TOKEN" -o pdfs_compras.zip \
  "$SIRE/empresas/$RUC/periodos/$PERIODO/libros/compras/pdfs/zip"

# ZIP de una solicitud masiva terminada
curl -s -H "Authorization: Bearer $TOKEN" -o solicitud.zip "$SIRE/solicitudes/<solicitud_id>/zip"
```

## 10. Actualizar los datos antes de extraer (opcional: escribe en Sire)

La extracción de las secciones 4 a 9 solo lee. Si el proceso también debe traer
datos nuevos de SUNAT, hay rutas que **inician trabajos en segundo plano**: entran
a SUNAT con la clave SOL de la empresa, tardan minutos y se siguen con `/jobs`.
Úsalas con criterio: cada una abre un navegador en el servidor.

```bash
# Crear el periodo si no existe
curl -s -X POST "${H[@]}" -H "Content-Type: application/json" \
  -d "{\"periodo\": \"$PERIODO\"}" "$SIRE/empresas/$RUC/periodos"

# Traer la propuesta del SIRE (lista de comprobantes) de un libro
curl -s -X POST "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/libros/compras/propuesta"

# Traer el detalle (glosa) y el PDF de cada comprobante → devuelve job_id
curl -s -X POST "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/libros/compras/detalle"

# Clasificar las cuentas contables del libro → devuelve job_id
curl -s -X POST "${H[@]}" "$SIRE/empresas/$RUC/periodos/$PERIODO/libros/compras/clasificacion"

# Todo lo anterior para varias empresas y periodos de una vez
curl -s -X POST "${H[@]}" -H "Content-Type: application/json" \
  -d '{"empresas": ["20603391692", "10209911031"], "periodos": ["202608", "202609"], "clasificar": true}' \
  "$SIRE/solicitudes"
#  "empresas": "todas" y "periodos": "todos" también son válidos

# Esperar a que termine un trabajo
curl -s "${H[@]}" "$SIRE/jobs/<job_id>" | jq '{estado, progreso, error}'
```

## 11. Script completo: extraer todo a NDJSON

Recorre todas las empresas, sus periodos y ambos libros, y deja un archivo por
tabla, listo para cargar en BigQuery, Postgres, DuckDB o similar.

```bash
#!/usr/bin/env bash
set -euo pipefail
SIRE="https://apaclla-web.p7slsc.easypanel.host/api/v1"
: "${SIRE_EMAIL:?exporta SIRE_EMAIL}" "${SIRE_PASSWORD:?exporta SIRE_PASSWORD}"
TOKEN=$(jq -n --arg e "$SIRE_EMAIL" --arg p "$SIRE_PASSWORD" '{email: $e, password: $p}' \
  | curl -sf -X POST "$SIRE/auth/token" -H "Content-Type: application/json" -d @- \
  | jq -r .access_token)
H=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/json")
SALIDA="extraccion_$(date +%Y%m%d_%H%M%S)"; mkdir -p "$SALIDA"

curl -sf "${H[@]}" "$SIRE/empresas" > "$SALIDA/empresas.json"

for RUC in $(jq -r '.[].ruc' "$SALIDA/empresas.json"); do
  curl -sf "${H[@]}" "$SIRE/empresas/$RUC/periodos" \
    | jq -c --arg ruc "$RUC" '.[] | . + {ruc: $ruc}' >> "$SALIDA/periodos.ndjson"

  for PERIODO in $(curl -sf "${H[@]}" "$SIRE/empresas/$RUC/periodos" | jq -r '.[].periodo'); do
    for LIBRO in compras ventas; do
      SKIP=0
      while :; do
        PAGINA=$(curl -sf "${H[@]}" \
          "$SIRE/empresas/$RUC/periodos/$PERIODO/comprobantes?libro=$LIBRO&limit=500&skip=$SKIP")
        N=$(jq length <<<"$PAGINA")
        jq -c --arg ruc "$RUC" --arg periodo "$PERIODO" \
          '.[] | . + {ruc: $ruc, periodo: $periodo}' <<<"$PAGINA" >> "$SALIDA/comprobantes.ndjson"
        [ "$N" -lt 500 ] && break
        SKIP=$((SKIP + 500))
      done
    done
  done

  curl -sf "${H[@]}" "$SIRE/empresas/$RUC/clasificaciones-frecuentes" \
    | jq -c --arg ruc "$RUC" '.[] | . + {ruc: $ruc}' >> "$SALIDA/clasificaciones_frecuentes.ndjson"
done

wc -l "$SALIDA"/*.ndjson
```

La misma idea en Python, escribiendo un CSV plano de comprobantes (con la
clasificación aplanada en columnas):

```python
import csv
import os

import requests

SIRE = "https://apaclla-web.p7slsc.easypanel.host/api/v1"
s = requests.Session()
login = s.post(
    f"{SIRE}/auth/token",
    json={"email": os.environ["SIRE_EMAIL"], "password": os.environ["SIRE_PASSWORD"]},
    timeout=60,
)
login.raise_for_status()
s.headers["Authorization"] = f"Bearer {login.json()['access_token']}"  # dura 5 horas


def paginas(url, limite=500, **params):
    skip = 0
    while True:
        r = s.get(url, params={**params, "limit": limite, "skip": skip}, timeout=60)
        r.raise_for_status()
        filas = r.json()
        yield from filas
        if len(filas) < limite:
            return
        skip += limite


filas = []
for empresa in s.get(f"{SIRE}/empresas", timeout=60).json():
    ruc = empresa["ruc"]
    for p in s.get(f"{SIRE}/empresas/{ruc}/periodos", timeout=60).json():
        for libro in ("compras", "ventas"):
            url = f"{SIRE}/empresas/{ruc}/periodos/{p['periodo']}/comprobantes"
            for c in paginas(url, libro=libro):
                cc = c.pop("clasificacion_contable") or {}
                for anidado in ("detalle_sunat", "detracciones", "documentos_modificados", "detraccion", "pdf_sunat"):
                    c.pop(anidado, None)  # a tablas aparte si se necesitan
                filas.append({
                    "ruc": ruc, "periodo": p["periodo"], **c,
                    "cuenta_base": cc.get("cuenta_base"),
                    "cuenta_total": cc.get("cuenta_total"),
                    "clasificacion": cc.get("clasificacion"),
                    "requiere_revision": cc.get("requiere_revision"),
                    "confianza": cc.get("confianza"),
                })

with open("comprobantes.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=sorted({k for fila in filas for k in fila}))
    w.writeheader()
    w.writerows(filas)
print(len(filas), "comprobantes")
```

## 12. Errores

| Código | Significado | Qué hacer |
|---|---|---|
| 401 `Correo o contraseña incorrectos` | Credenciales mal escritas | Revisar el correo y la contraseña |
| 401 `… venció` | La contraseña caducó | Pedir una nueva a Apaclla |
| 401 `Token expirado` / `Token inválido` | Pasaron las 5 horas o el token está mal copiado | Volver a llamar a `/auth/token` |
| 403 | La cuenta fue desactivada | Contactar a Apaclla |
| 404 | RUC, periodo o comprobante inexistente | Revisar el RUC (11 dígitos) y el periodo (`YYYYMM`) |
| 409 | Ya hay un trabajo igual en curso | Esperar y consultar `/jobs` |
| 422 | Parámetro con formato inválido (p. ej. `libro=venta`) | Revisar la sección 3 |
| 429 | Demasiadas peticiones seguidas | Esperar un minuto |
| 502 / 503 | SUNAT no respondió | Reintentar más tarde |
