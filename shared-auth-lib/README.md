# shared-auth-lib

Librería compartida de autenticación JWT para todos los microservicios del ecosistema. Provee verificación de tokens, control de acceso por rol/permiso y dependencias FastAPI reutilizables.

## Integración en un servicio

Declarar como dependencia de workspace en el `pyproject.toml` del servicio:

```toml
dependencies = [
    "shared-auth-lib",
    ...
]

[tool.uv.sources]
shared-auth-lib = { workspace = true }
```

## Uso

```python
from shared_auth_lib.auth_utils import verify_jwt, require_role, require_permission, TokenPayload

# Verificar token
@router.get("/recurso")
async def endpoint(token: TokenPayload = Depends(verify_jwt)):
    user_id = token.sub
    role = token.role

# Restringir por rol
@router.post("/admin/accion")
async def accion_admin(token: TokenPayload = Depends(require_role("ADMIN"))):
    ...

# Restringir por permiso
@router.get("/datos-sensibles")
async def datos(token: TokenPayload = Depends(require_permission("coso.write"))):
    ...
```

## Variables requeridas en cada servicio consumidor

Deben tener exactamente los mismos valores que AUTH-API:

```bash
JWT_SECRET_KEY=A
JWT_ALGORITHM=B
JWT_ISSUER=C
JWT_AUDIENCE=D
```

Si `JWT_SECRET_KEY`, `JWT_ISSUER` o `JWT_AUDIENCE` no coinciden con el token emitido por AUTH-API, todos los endpoints protegidos devolverán `401`.
