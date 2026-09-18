import os

os.environ.setdefault("JWT_SECRET_KEY", "clave-de-prueba")
os.environ.setdefault("SOL_USER_CRYPTO_KEY", "clave-de-cifrado-de-prueba")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_FACTURASDB_NAME", "test_sire")
os.environ.setdefault("GOOGLE_CLIENT_ID", "cliente-de-prueba.apps.googleusercontent.com")
# Sin esto la allowlist arrancaria vacia y todo responderia 403: el campo falla
# cerrado a proposito (ver app/core/config.py).
os.environ.setdefault("GOOGLE_ALLOWED_EMAILS", "prueba@example.com")
