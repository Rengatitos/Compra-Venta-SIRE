# API de Sire para análisis de datos

Cómo extraer los datos de Sire —empresas, periodos, comprobantes de compras y
ventas, su clasificación contable, comprobantes recibidos por el bot y los
agregados del panel— para cargarlos en un almacén de datos y transformarlos allí.

## 1. Conexión

| | |
|---|---|
| **URL base de la API** | `https://apaclla-web.p7slsc.easypanel.host/api/v1` |
| Salud (sin sesión) | `https://apaclla-web.p7slsc.easypanel.host/health` |
| Formato | JSON (UTF-8). Las exportaciones devuelven Excel, PDF o ZIP. |
| Autenticación | `Authorization: Bearer <token>` en todas las rutas salvo `/health` y el login |
| Vigencia del token | **2 horas**. Al vencer, la API responde `401 Token expirado`: se vuelve a pedir. |

Variables que usan todos los ejemplos:

```bash
export SIRE="https://apaclla-web.p7slsc.easypanel.host/api/v1"
export TOKEN="<token de la sección 2>"
export RUC="20603391692"      # 11 dígitos
export PERIODO="202609"       # YYYYMM
```

Comprobar la conexión:

```bash
curl -s https://apaclla-web.p7slsc.easypanel.host/health
# {"status":"ok"}
```

## 2. Obtener el token

### Opción recomendada — Cuenta de API (correo y contraseña)

Sin Google, sin `gcloud` y sin abrir el panel en cada ejecución.

Una sola vez, un administrador entra al panel → botón **Accesos al panel** →
sección **Cuentas de API**, escribe el correo (por ejemplo
`administrador@apaclla.au.pe`), elige el rol y cuándo vence la contraseña, y pulsa
**Crear cuenta y generar contraseña**. Sire muestra la contraseña **una sola vez**
junto con el curl listo para copiar; solo guarda su hash.

En cada ejecución:

```bash
export TOKEN=$(curl -s -X POST "$SIRE/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"email": "administrador@apaclla.au.pe", "password": "<contraseña generada>"}' \
  | jq -r .access_token)
```

- Respuesta: la misma que el login con Google (`access_token`, `token_type`,
  `usuario`). El token dura 2 horas; al vencer se vuelve a pedir igual.
- La contraseña **vence** a los días elegidos (30 a 365). Antes de eso, o si se
  filtra, se pulsa **Nueva contraseña** en el panel: la anterior deja de servir en
  el acto. **Eliminar** la cuenta corta también los tokens ya emitidos.
- Errores: `401 Correo o contraseña incorrectos`, `401 … venció` (hay que
  regenerarla) y `429` a partir de 5 intentos por minuto.
- Guarda la contraseña en el gestor de secretos del ELT (variable de entorno,
  Secret Manager…), nunca en el código.

### Alternativa — Cuenta de Google

Las personas entran con una cuenta de Google que un administrador haya autorizado
en el panel (**Cuentas con acceso**). La API cambia el *ID token* de Google por
un token de Sire:

```
POST /api/v1/auth/google   {"credential": "<ID token de Google>"}
→ {"access_token": "...", "token_type": "bearer", "usuario": {"email": ..., "rol": ...}}
```

El ID token tiene que estar emitido para el cliente web de Sire, así que su
audiencia (`aud`) debe ser exactamente:

```
257729885873-r2f868plc3gsr2jhe2db32hp9igg93ua.apps.googleusercontent.com
```

#### Cuenta de servicio de Google Cloud

Una sola vez:

1. En Google Cloud, crear una cuenta de servicio para el ELT, por ejemplo
   `sire-elt@<proyecto>.iam.gserviceaccount.com`.
2. Dar a quien ejecuta el proceso el rol **Creador de tokens de cuenta de
   servicio** (`roles/iam.serviceAccountTokenCreator`) sobre esa cuenta, o
   descargar una clave JSON de ella.
3. Pedir a un administrador de Sire que agregue ese correo en **Cuentas con
   acceso** con rol **usuario**. Ese rol lee los datos y puede lanzar procesos,
   pero no gestiona accesos. Sire no tiene un rol de solo lectura: el proceso ELT
   debe limitarse a las rutas de lectura (secciones 4 a 9).

En cada ejecución:

```bash
AUD="257729885873-r2f868plc3gsr2jhe2db32hp9igg93ua.apps.googleusercontent.com"
SA="sire-elt@<proyecto>.iam.gserviceaccount.com"

# Con impersonación (sin archivos de clave):
ID_TOKEN=$(gcloud auth print-identity-token \
  --impersonate-service-account="$SA" --audiences="$AUD" --include-email)

# …o con la clave JSON de la cuenta de servicio:
# gcloud auth activate-service-account --key-file=sire-elt.json
# ID_TOKEN=$(gcloud auth print-identity-token --audiences="$AUD" --include-email)

export TOKEN=$(curl -s -X POST "$SIRE/auth/google" \
  -H "Content-Type: application/json" \
  -d "{\"credential\": \"$ID_TOKEN\"}" | jq -r .access_token)
```

`--include-email` es obligatorio: Sire rechaza un ID token sin correo verificado.

#### Token de una sesión del panel (pruebas manuales)

1. Entrar al panel `https://apaclla-web.p7slsc.easypanel.host` con Google.
2. DevTools (F12) → **Application** → **Session Storage** → clave `sire.sesion`.
3. Copiar el valor de `token` y exportarlo como `TOKEN`. Dura 2 horas.

### Verificar el token

```bash
curl -s "$SIRE/auth/yo" -H "Authorization: Bearer $TOKEN"
# {"email":"sire-elt@…","nombre":null,"foto":null,"rol":"usuario"}
```

## 3. Convenciones

- **`periodo`**: `YYYYMM` (septiembre de 2026 = `202609`).
- **`libro`**: `ventas` o `compras`.
- **`ruc`**: 11 dígitos, sin espacios.
- **Importes**: números en la moneda del comprobante (`moneda`, con `tipo_cambio` si es USD).
- **Paginación**: `limit` y `skip`. Se pide página a página hasta que llegue
  una lista más corta que `limit`.
- **Límites**: el login admite 10 peticiones/min; las de lectura no tienen un
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
: "${TOKEN:?exporta TOKEN (sección 2)}"
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
s.headers["Authorization"] = f"Bearer {os.environ['TOKEN']}"


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
| 401 `Token expirado` / `Token inválido` | El token venció (2 h) o está mal copiado | Pedir uno nuevo (sección 2) |
| 401 en `/auth/google` | ID token de Google inválido o con otra audiencia | Revisar `--audiences` e `--include-email` |
| 403 | La cuenta no está en **Cuentas con acceso** | Pedir acceso a un administrador |
| 404 | RUC, periodo o comprobante inexistente | Revisar el RUC (11 dígitos) y el periodo (`YYYYMM`) |
| 409 | Ya hay un trabajo igual en curso | Esperar y consultar `/jobs` |
| 422 | Parámetro con formato inválido (p. ej. `libro=venta`) | Revisar la sección 3 |
| 429 | Demasiadas peticiones seguidas | Esperar un minuto |
| 502 / 503 | SUNAT o Google no respondieron | Reintentar más tarde |
