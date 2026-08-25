"""Shared authentication library for microservices."""

from shared_auth_lib.auth_utils import (
    AuthError,
    TokenPayload,
    require_permission,
    require_role,
    require_role_or_permission,
    verify_jwt,
)

__version__ = "1.0.0"
__all__ = [
    "TokenPayload",
    "AuthError",
    "verify_jwt",
    "require_role",
    "require_permission",
    "require_role_or_permission",
]
