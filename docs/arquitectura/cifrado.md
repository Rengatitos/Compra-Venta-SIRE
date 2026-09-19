# Cifrado de contraseñas SOL

Las contraseñas SOL (las credenciales de la empresa ante SUNAT Operaciones en Línea) se cifran de forma **reversible**, no se hashean, porque el sistema necesita la contraseña en texto plano para autenticar contra la API oficial de SUNAT y para el scraping del portal.

## Cómo funciona

[encryption.py](../../app/core/encryption.py) usa Fernet (cifrado simétrico autenticado) de la librería `cryptography`:

1. La semilla es `SOL_USER_CRYPTO_KEY` si está definida; si no, cae a `JWT_SECRET_KEY`. Ver [_get_fernet](../../app/core/encryption.py).
2. La semilla se pasa por SHA-256 para obtener 32 bytes, y esos bytes se codifican en base64 URL-safe, que es el formato que Fernet exige para su clave.
3. [encrypt_password](../../app/core/encryption.py) y [decrypt_password](../../app/core/encryption.py) delegan directamente en Fernet.

## Dónde se usa

- Al crear o actualizar una empresa ([empresas.py](../../app/api/v1/routes/empresas.py)), la contraseña se cifra antes de guardarse.
- Al renovar el token de SUNAT ([empresas.py](../../app/api/v1/routes/empresas.py)), al obtener el token OAuth inicial ([sunat/auth.py](../../app/services/sunat/auth.py)), al hacer scraping ([scraping_sunat.py](../../app/services/scraping_sunat.py)) y al consultar detracciones ([sunat/detracciones.py](../../app/services/sunat/detracciones.py)), la contraseña se descifra para enviarla a SUNAT.

La contraseña SOL **no interviene en el acceso al panel**: eso se hace con una cuenta de Google (ver [autenticación](autenticacion.md)). Su único uso es hablar con SUNAT.

## Implicación de rotar secretos

Si `SOL_USER_CRYPTO_KEY` (o, en su ausencia, `JWT_SECRET_KEY`) cambia, **todas las contraseñas ya cifradas dejan de poder descifrarse**: no hay versionado de clave ni migración automática. Rotar ese secreto en producción exige re-cifrar todas las contraseñas SOL almacenadas, o pedirle a cada empresa que las vuelva a registrar.

El caso que más fácil se cuela: rotar `JWT_SECRET_KEY` para invalidar sesiones. En un despliegue sin `SOL_USER_CRYPTO_KEY` definida eso tumba el scraping, las detracciones y la renovación del token de SUNAT, y el síntoma aparece horas después. Las sesiones se invalidan con el claim `tipo` del token, no rotando el secreto (ver [autenticación](autenticacion.md)).
