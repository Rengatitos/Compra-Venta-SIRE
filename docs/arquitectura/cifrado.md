# Cifrado de contraseñas SOL

Todo el código relevante está en [encryption.py](../../app/core/encryption.py).

Las contraseñas SOL (las credenciales SUNAT de cada empresa) se guardan cifradas, no hasheadas, porque el sistema necesita recuperarlas en texto plano para autenticar contra la API OAuth de SUNAT ([obtener_token_api_oficial](../../app/services/sire_service.py:15)) y, opcionalmente, para el login del scraping con Playwright.

## Derivación de la clave

La función [_get_fernet](../../app/core/encryption.py:6) deriva una clave de cifrado determinística: toma la variable de entorno SOL_USER_CRYPTO_KEY si está definida; si no, usa JWT_SECRET_KEY como semilla. La intención, según el propio criterio del código, es priorizar una clave dedicada para el cifrado de contraseñas SOL, pero tolerar reutilizar el secreto del JWT si no se configuró una clave separada. La semilla elegida se pasa por un hash SHA-256 y el resultado de 32 bytes se codifica para obtener una clave válida para el esquema de cifrado usado (Fernet, de la librería cryptography).

Las funciones [encrypt_password](../../app/core/encryption.py:14) y [decrypt_password](../../app/core/encryption.py:18) son wrappers directos sobre las operaciones de cifrado y descifrado de esa clave derivada.

## Implicación de rotación de secretos

Como la clave de cifrado se deriva de SOL_USER_CRYPTO_KEY (o, en su ausencia, de JWT_SECRET_KEY), rotar JWT_SECRET_KEY sin haber fijado antes SOL_USER_CRYPTO_KEY invalida el descifrado de todas las contraseñas SOL ya guardadas: quedarían indescifrables hasta que se restaure el valor anterior de la clave. En producción conviene fijar SOL_USER_CRYPTO_KEY explícitamente desde el principio y nunca rotarla sin un plan de re-cifrado de los datos existentes.

Ver también [inicio](../inicio.md) para el detalle de estas dos variables de entorno, y [modelo de datos de usuarios SOL](../modelo-datos/sol-users.md) para el campo donde se guarda la contraseña cifrada.
