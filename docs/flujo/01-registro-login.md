# Flujo — Registro y login

## Registro de un usuario SOL

Se crea un usuario SOL con el endpoint [create_user](../endpoints/sol-users.md): RUC, usuario SOL, contraseña SOL (que se cifra antes de guardarse, ver [cifrado](../arquitectura/cifrado.md)), y opcionalmente las credenciales OAuth del cliente SIRE registrado en SUNAT, junto con los identificadores del sistema externo que integra esta API (tenant, cliente y cuenta).

Estas credenciales OAuth se ingresan manualmente, igual que cualquier otro campo del usuario. Anteriormente existía un flujo de scraping que las obtenía automáticamente navegando el portal SOL con Playwright; ese scraping de credenciales fue eliminado por completo del código. Lo único que queda de Playwright en el sistema es la extracción del detalle de ítems de facturas ya sincronizadas, descrita en [flujo de scraping de detalle](04-scraping-detalle.md).

## Login

El endpoint [login](../endpoints/sol-users.md) recibe el RUC, el usuario y la contraseña; descifra la contraseña almacenada y la compara en texto plano contra la enviada. Si coincide, se emite un token que incluye el identificador de usuario y el RUC, válido por la cantidad de horas configurada (ver [inicio](../inicio.md) y [autenticación](../arquitectura/autenticacion.md)).
