# Flujo — Acceso y alta de empresas

## Acceso

Se entra con una **cuenta de Google**. El navegador obtiene un ID token de Google Identity Services y [POST /api/v1/auth/google](../endpoints/empresas.md) lo cambia por el JWT propio, válido `JWT_EXPIRE_HOURS` horas (ver [inicio](../inicio.md) y [autenticación](../arquitectura/autenticacion.md)).

Quién puede entrar lo decide `GOOGLE_ALLOWED_EMAILS`, una lista de correos en el entorno. No hay colección de usuarios en Mongo: con un solo usuario, una tabla entera sería estructura sin contenido. Una lista vacía no deja entrar a nadie, que es el fallo seguro.

Una vez dentro se elige la empresa sobre la que trabajar, y se puede cambiar de una a otra desde la barra superior **sin volver a iniciar sesión**.

## Alta de una empresa

Se registra con [POST /api/v1/empresas](../endpoints/empresas.md), que ahora **exige sesión**. En el panel es la pantalla `/empresas/nueva`, alcanzable desde el selector de cuentas y servida fuera del armazón, porque la barra superior anuncia la empresa activa y no la que se está dando de alta. Recibe: RUC, nombre opcional, usuario SOL, contraseña SOL (que se cifra antes de guardarse, ver [cifrado](../arquitectura/cifrado.md)), y opcionalmente las credenciales OAuth del cliente SIRE (`sunat_client_id`/`sunat_client_secret`) si la empresa tiene las suyas propias registradas en SUNAT — si no las tiene, se usan las globales de `SUNAT_CLIENT_ID`/`SUNAT_CLIENT_SECRET` como respaldo.

Estas credenciales OAuth se ingresan manualmente. No existe un flujo de scraping que las obtenga automáticamente navegando el portal SOL. Lo único que hace Playwright en el sistema es la extracción del detalle de ítems de comprobantes ya sincronizados, descrita en [flujo de extracción de detalle](04-extraccion-detalle.md).

## Las credenciales SOL ya no son la llave del panel

Se siguen guardando cifradas en cada empresa porque el sistema las necesita en claro para hablar con SUNAT, pero su único uso es ése:

- el OAuth de la API SIRE ([sunat/auth.py](../../app/services/sunat/auth.py)),
- el login en el portal SOL con Playwright ([scraping_sunat.py](../../app/services/scraping_sunat.py)),
- la consulta de detracciones ([sunat/detracciones.py](../../app/services/sunat/detracciones.py)).

## Token de la API SIRE

El JWT propio de la aplicación no tiene relación con el token OAuth que la empresa necesita para hablar con la API oficial de SUNAT. Ese segundo token se obtiene la primera vez que se sincroniza una propuesta ([flujo de sincronización](03-sincronizacion-propuesta.md)) o explícitamente vía [POST /api/v1/empresas/{ruc}/token-sunat](../endpoints/empresas.md), y se guarda en el documento de la empresa para reutilizarse en llamadas siguientes.
