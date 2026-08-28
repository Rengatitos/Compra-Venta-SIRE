# Flujo — Registro y login

## Registro de una empresa

Se registra una empresa con [POST /api/v1/empresas](../endpoints/empresas.md): RUC, usuario SOL, contraseña SOL (que se cifra antes de guardarse, ver [cifrado](../arquitectura/cifrado.md)), y opcionalmente las credenciales OAuth del cliente SIRE (`sunat_client_id`/`sunat_client_secret`) si la empresa tiene las suyas propias registradas en SUNAT — si no las tiene, se usan las globales de `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET` como respaldo.

Estas credenciales OAuth se ingresan manualmente. No existe un flujo de scraping que las obtenga automáticamente navegando el portal SOL. Lo único que hace Playwright en el sistema es la extracción del detalle de ítems de comprobantes ya sincronizados, descrita en [flujo de extracción de detalle](04-extraccion-detalle.md).

## Login

[POST /api/v1/auth/login](../endpoints/empresas.md) recibe RUC, usuario y contraseña; descifra la contraseña almacenada y la compara en texto plano contra la enviada. Si coincide, se emite un JWT con `empresa_id` y `ruc`, válido por `JWT_EXPIRE_HOURS` horas (ver [inicio](../inicio.md) y [autenticación](../arquitectura/autenticacion.md)).

## Token de la API SIRE

El JWT propio de la aplicación no tiene relación con el token OAuth que la empresa necesita para hablar con la API oficial de SUNAT. Ese segundo token se obtiene la primera vez que se sincroniza una propuesta ([flujo de sincronización](03-sincronizacion-propuesta.md)) o explícitamente vía [POST /api/v1/empresas/{ruc}/token-sunat](../endpoints/empresas.md), y se guarda en el documento de la empresa para reutilizarse en llamadas siguientes.
