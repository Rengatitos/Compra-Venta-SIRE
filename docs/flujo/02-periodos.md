# Flujo — Crear periodo

[POST /api/v1/empresas/{ruc}/periodos](../endpoints/periodos.md) crea un periodo fiscal en estado `pendiente`. El formato se valida contra [PERIODO_RE](../../app/domain/periodo.py:5) (año `20xx`, mes `01`-`12`), tanto en el schema de creación como en la dependencia [periodo_valido](../../app/api/v1/deps.py:26) que usan el resto de las rutas que reciben `{periodo}` como parámetro de path.

El periodo es único por empresa: la unicidad está garantizada tanto por la validación del schema como por el índice único `(empresa_id, periodo)` en Mongo (ver [modelo de datos de periodos](../modelo-datos/periodos.md)).
