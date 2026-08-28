# Cifrado de contraseñas SOL

Las contraseñas SOL (las credenciales de la empresa ante SUNAT Operaciones en Línea) se cifran de forma **reversible**, no se hashean, porque el sistema necesita la contraseña en texto plano para autenticar contra la API oficial de SUNAT y para el scraping del portal.

## Cómo funciona

[encryption.py](../../app/core/encryption.py) usa Fernet (cifrado simétrico autenticado) de la librería `cryptography`:

1. La semilla es `SOL_USER_CRYPTO_KEY` si está definida; si no, cae a `JWT_SECRET_KEY`. Ver [_get_fernet](../../app/core/encryption.py:6).
2. La semilla se pasa por SHA-256 para obtener 32 bytes, y esos bytes se codifican en base64 URL-safe, que es el formato que Fernet exige para su clave.
3. [encrypt_password](../../app/core/encryption.py:14) y [decrypt_password](../../app/core/encryption.py:18) delegan directamente en Fernet.

## Dónde se usa

- Al crear o actualizar una empresa ([empresas.py](../../app/api/v1/routes/empresas.py)), la contraseña se cifra antes de guardarse.
- Al hacer login ([auth.py](../../app/api/v1/routes/auth.py)), al renovar el token de SUNAT ([empresas.py](../../app/api/v1/routes/empresas.py:96)), al obtener el token OAuth inicial ([sunat/auth.py](../../app/services/sunat/auth.py:65)) y al hacer scraping ([scraping_sunat.py](../../app/services/scraping_sunat.py)), la contraseña se descifra para compararla o enviarla a SUNAT.

## Implicación de rotar secretos

Si `SOL_USER_CRYPTO_KEY` (o, en su ausencia, `JWT_SECRET_KEY`) cambia, **todas las contraseñas ya cifradas dejan de poder descifrarse**: no hay versionado de clave ni migración automática. Rotar ese secreto en producción exige re-cifrar todas las contraseñas SOL almacenadas, o pedirle a cada empresa que las vuelva a registrar.
