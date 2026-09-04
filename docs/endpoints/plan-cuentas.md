# Endpoints — Maestro de cuentas

El plan contable (PCGE) de la empresa, tal como lo exporta Contasis. Es el catálogo con el que se interpreta cada código de cuenta del registro.

No confundirlo con `app/resources/rag_contasis/plan_cuentas.csv`, que es un **corpus de recuperación** estático y común a todas las empresas, indexado en `rag_account_plan_index` para la clasificación con IA. El maestro de esta colección es un dato de negocio **por empresa** y no se reindexa al subirlo.

## `POST /api/v1/empresas/{ruc}/plan-cuentas`

[cargar_cuentas](../../app/api/v1/routes/plan_cuentas.py:41). Multipart con el campo `archivo` (`.xlsx` o `.xlsm`). Límite: 5/minuto.

**Reemplaza el maestro completo**, no fusiona: el archivo es la fuente de verdad, y una cuenta que Contasis dejó de exportar es una cuenta que ya no existe. Fusionando se quedaría viva para siempre.

```json
{ "mensaje": "Maestro de cuentas cargado desde «CUENTAS CONTABLES.xlsx»", "cuentas": 2881 }
```

`400` con el motivo si el archivo no se puede leer: no es un Excel, no tiene la hoja esperada, o no tiene ninguna cuenta con código utilizable. Son problemas que el usuario puede arreglar subiendo el archivo correcto, así que no salen como error interno.

### El formato tiene dos trampas

El parser vive en [app/domain/plan_cuentas.py](../../app/domain/plan_cuentas.py) y es lógica pura —sin openpyxl ni Mongo—, así que se prueba contra el archivo real sin levantar nada. Lo que resuelve:

1. **El código no está en una columna, está en tres.** La jerarquía se dibuja con la sangría: el elemento va en la primera columna, la cuenta en la segunda, y la subcuenta con sus divisionarias en la tercera. Cada fila trae el código en una sola de las tres, y cuál es determina el `nivel`. Leyendo sólo la primera columna se pierden 2.793 de las 2.881 cuentas del archivo real.
2. **La última fila no es una cuenta.** Contasis firma el archivo con «Generado automáticamente por GESTIÓN CONTABLE FINANCIERO PREMIUM 26.00 - NewContaSis el 26/06/2026» metido en la columna del código. Leído de corrido entra como una cuenta de 98 caracteres.

Las cabeceras se localizan **por texto** (`CUENTA`, `DESCRIPCION`, `TIPO`, `ANALISIS`, `CENTRO DE COSTOS`) y no por posición, porque las columnas se han movido entre versiones del exportador. La hoja se busca por nombre (`PLAN DE CUENTAS`) y, si no está, por la primera que tenga esas cabeceras.

Todas las celdas se recortan: Contasis rellena a ancho fijo con espacios (`'01        '`), y sin recortar no casa nada aguas abajo — ni el índice único, ni el buscador, ni el cruce con la clasificación.

## `GET /api/v1/empresas/{ruc}/plan-cuentas`

[listar_cuentas](../../app/api/v1/routes/plan_cuentas.py:25). Paginado (`limit` ≤ 3000, `skip`) y ordenado por código.

`busqueda` filtra por código **y** por descripción a la vez, sin distinguir mayúsculas: el contador conoce el número de unas cuentas y el nombre de otras. El texto se neutraliza como expresión regular, así que un `(` o un `*` tecleado en el buscador no tumba la consulta.

```json
{
  "cuentas": [
    { "cuenta": "2521", "descripcion": "COMBUSTIBLES - Suministros", "tipo": "Activo",
      "analisis": "Ninguno", "centro_costos": "Sin centro de Costos", "nivel": 3 }
  ],
  "total": 7
}
```

`total` es el que casa con el filtro, no el de la página: es lo que permite paginar y mostrar «N de M» sin una segunda llamada.

## `DELETE /api/v1/empresas/{ruc}/plan-cuentas`

[eliminar_cuentas](../../app/api/v1/routes/plan_cuentas.py:80). Borra el maestro de la empresa y devuelve cuántas cuentas se eliminaron. También se borra en cascada al eliminar la empresa.

## Colección `plan_cuentas`

Índice único `(empresa_id, cuenta)` más un índice `(empresa_id, descripcion)` para el buscador: son casi tres mil cuentas por empresa y sin él cada tecleo recorre la colección entera.

```json
{
  "empresa_id": "6a934217fb0e2a9d9780f7ab",
  "cuenta": "0111",
  "descripcion": "BIENES EN PRESTAMO - Entregados",
  "tipo": "Orden",
  "analisis": "Documentos",
  "centro_costos": "Sin centro de Costos",
  "nivel": 3
}
```
