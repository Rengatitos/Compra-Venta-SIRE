# Flujo — Acceso y alta de empresas

## Acceso

Se entra con una **cuenta de Google**. El navegador obtiene un ID token de Google Identity Services y [POST /api/v1/auth/google](../endpoints/empresas.md) lo cambia por el JWT propio, válido `JWT_EXPIRE_HOURS` horas (ver [inicio](../inicio.md) y [autenticación](../arquitectura/autenticacion.md)).

Quién puede entrar lo decide `GOOGLE_ALLOWED_EMAILS`, una lista de correos en el entorno. No hay colección de usuarios en Mongo: con un solo usuario, una tabla entera sería estructura sin contenido. Una lista vacía no deja entrar a nadie, que es el fallo seguro.

Una vez dentro se elige la empresa sobre la que trabajar, y se puede cambiar de una a otra desde la barra superior **sin volver a iniciar sesión**.

## Alta de empresas

Hay dos modalidades en la pantalla `/empresas/nueva`, servida fuera del armazón porque la barra superior anuncia la empresa activa y no la que se está dando de alta:

- **Carga masiva** (la que abre por defecto): [POST /api/v1/empresas/cargas](../endpoints/empresas.md) con un Excel de razón social, RUC, usuario y contraseña SOL en las columnas A a D.
- **Individual**: [POST /api/v1/empresas](../endpoints/empresas.md), con RUC, razón social opcional, usuario y contraseña SOL (cifrada antes de guardarse, ver [cifrado](../arquitectura/cifrado.md)) y, opcionalmente, el client_id y la clave del API SUNAT.

En los dos casos el RUC se valida con su dígito verificador y uno ya registrado se rechaza sin tocar el existente. La empresa queda registrada en el acto, con `registro` (quién, cuándo, cómo). Lo que depende de SUNAT se completa en la [cola](../arquitectura/cola.md), con reintentos:

1. Credenciales del API SUNAT desde SOL, si faltan ([credenciales_sunat_service](../../app/services/credenciales_sunat_service.py)). En la masiva las pide la cola; en la individual, el formulario justo después del alta.
2. Token de la API SIRE, que trae el CIIU principal.
3. Ficha RUC: actividades económicas y, si el token no trajo CIIU, el de la actividad principal.
4. CIIU y rubro guardados en la empresa.

Si algún paso falla, la empresa se conserva como «agregada con observaciones». El resultado por fila queda en `cargas_empresas` y se descarga como reporte Excel.

## Las credenciales SOL ya no son la llave del panel

Se siguen guardando cifradas en cada empresa porque el sistema las necesita en claro para hablar con SUNAT, pero su único uso es ése:

- el OAuth de la API SIRE ([sunat/auth.py](../../app/services/sunat/auth.py)),
- el login en el portal SOL con Playwright ([scraping_sunat.py](../../app/services/scraping_sunat.py)),
- la consulta de detracciones ([sunat/detracciones.py](../../app/services/sunat/detracciones.py)).

## Token de la API SIRE

El JWT propio de la aplicación no tiene relación con el token OAuth que la empresa necesita para hablar con la API oficial de SUNAT. Ese segundo token se obtiene la primera vez que se sincroniza una propuesta ([flujo de sincronización](03-sincronizacion-propuesta.md)) o explícitamente vía [POST /api/v1/empresas/{ruc}/token-sunat](../endpoints/empresas.md), y se guarda en el documento de la empresa para reutilizarse en llamadas siguientes.
