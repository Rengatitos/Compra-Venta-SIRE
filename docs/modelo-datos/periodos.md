# Modelo de datos — periodos

Un periodo fiscal de sincronización SIRE para un usuario. Poblada por [create_period](../../app/api/routes/periods.py:11).

| Campo | Tipo | Descripción |
|---|---|---|
| usuario | str | Id de Mongo del usuario SOL, como cadena de texto. |
| periodo | str | Formato año-mes de seis dígitos. |
| estado | str | Pendiente al crearse; terminado cuando la sincronización de la propuesta SIRE completa el proceso (con o sin comprobantes, incluyendo el caso en que SUNAT no tiene propuestas para ese periodo). Ver [flujo de sincronización SIRE](../flujo/03-sincronizacion-sire.md). |
| fecha de creación | str, ISO, sin zona horaria — una inconsistencia frente al campo equivalente de sol_users, que sí guarda la fecha con zona horaria UTC. |

Índice: único compuesto por usuario y periodo.
