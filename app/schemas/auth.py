from pydantic import BaseModel


class LoginGoogle(BaseModel):
    # Se llama `credential` porque es literalmente la clave con la que Google
    # Identity Services entrega el ID token en su callback: copiar el nombre
    # ahorra una capa de renombrado en el frontend.
    credential: str


class UsuarioResponse(BaseModel):
    email: str
    nombre: str | None = None
    foto: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    # El perfil viaja en el cuerpo y no dentro del JWT: la URL del avatar de
    # Google ronda los cien caracteres y engordaría la cabecera de todas las
    # peticiones. Así el panel puede pintar el correo sin decodificar el token.
    usuario: UsuarioResponse
