import hashlib
import base64
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    from app.core.config import settings
    # Priorizar la clave compartida para sol_user
    seed = settings.SOL_USER_CRYPTO_KEY or settings.JWT_SECRET_KEY
    key_bytes = hashlib.sha256(seed.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key_bytes)
    return Fernet(fernet_key)


def encrypt_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()


def decrypt_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()
