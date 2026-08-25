# Flujo — Crear periodo

El endpoint [create_period](../endpoints/periods.md) crea un periodo fiscal en estado pendiente. El formato del periodo se valida con una expresión regular que exige año 20xx y mes entre 01 y 12. El periodo es único por usuario: esa unicidad está garantizada tanto por la validación de la aplicación como por un índice único de Mongo (ver [modelo de datos de periodos](../modelo-datos/periodos.md)).
