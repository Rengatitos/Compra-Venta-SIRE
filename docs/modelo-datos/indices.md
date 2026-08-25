# Modelo de datos — Índices creados en el arranque

Todos estos índices se crean durante el [ciclo de vida](../arquitectura/ciclo-de-vida.md) de la aplicación, en [main.py](../../app/main.py:60).

- sol_users: índice sobre el RUC. Ver [modelo de datos — sol_users](sol-users.md).
- periodos: índice único compuesto por usuario y periodo. Ver [modelo de datos — periodos](periodos.md).
- facturas: índice compuesto por usuario y periodo; índice suelto sobre el número de serie; índice único parcial por usuario, periodo y número de serie, que solo aplica a documentos donde el número de serie es una cadena no vacía. Ver [modelo de datos — facturas](facturas.md).
- vector_global: índice sobre el nombre de documento dentro de metadata. Ver [modelo de datos — vector_global](vector-global.md).
- vector_users: índice compuesto por usuario y nombre de documento dentro de metadata. Ver [modelo de datos — vector_users](vector-users.md).

La creación del índice único parcial de facturas está protegida con un manejo de errores específico: si falla —por ejemplo, por datos duplicados preexistentes que la deduplicación de arranque no llegó a limpiar— el servicio sigue funcionando sin ese índice, registrando solo una advertencia en el log en vez de impedir que la aplicación termine de arrancar. Ver el detalle completo en [ciclo de vida](../arquitectura/ciclo-de-vida.md).
