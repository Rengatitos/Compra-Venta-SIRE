"""El portal devuelve el formulario de login de vez en cuando aunque las
credenciales sean correctas, y antes eso mataba el job entero. Estos tests
fijan las dos mitades del arreglo: que se reintente, y que unas credenciales
rechazadas de verdad NO se reintenten (SOL bloquea el usuario)."""

from __future__ import annotations

import pytest

from app.services import scraping_sunat


class PaginaFalsa:
    """Lo justo de la API de Playwright que usan el login y la evidencia."""

    def __init__(self) -> None:
        self.url = "https://api-seguridad.sunat.gob.pe/oauth2/loginMenuSol"
        self.esperas_ms: list[int] = []
        self.capturas: list[str] = []

    def wait_for_timeout(self, ms: int) -> None:
        self.esperas_ms.append(ms)

    def evaluate(self, expresion: str):
        return "function" if "login" in expresion else "undefined"

    def locator(self, _selector: str):
        return self

    def text_content(self) -> str:
        return "SUNAT Operaciones en Linea RUC DNI Iniciar sesion"

    def screenshot(self, path: str, full_page: bool = False) -> None:
        self.capturas.append(path)


@pytest.fixture
def pagina() -> PaginaFalsa:
    return PaginaFalsa()


def _login_que_falla(veces: int, monkeypatch, excepcion=None):
    """Sustituye `_hacer_login` por uno que falla las primeras `veces`."""
    fallo = excepcion or scraping_sunat.SesionSolError("formulario de login")
    intentos = {"n": 0}

    def falso(page, ruc, usuario, password):
        intentos["n"] += 1
        if intentos["n"] <= veces:
            raise fallo

    monkeypatch.setattr(scraping_sunat, "_hacer_login", falso)
    return intentos


def test_reintenta_y_entra_al_segundo_intento(pagina, monkeypatch, tmp_path):
    """Un rechazo transitorio no puede costar la extracción de un periodo."""
    monkeypatch.setattr(scraping_sunat, "LOG_DIR", tmp_path)
    intentos = _login_que_falla(1, monkeypatch)
    mensajes: list[str] = []

    scraping_sunat._login_con_reintentos(pagina, "20", "usr", "clave", mensajes.append)

    assert intentos["n"] == 2
    assert any("intento 2" in m for m in mensajes)
    # La espera entre intentos da tiempo a que SOL libere la sesión anterior.
    assert pagina.esperas_ms == [scraping_sunat.ESPERA_REINTENTO_LOGIN_MS]


def test_se_rinde_tras_agotar_los_intentos(pagina, monkeypatch, tmp_path):
    monkeypatch.setattr(scraping_sunat, "LOG_DIR", tmp_path)
    intentos = _login_que_falla(99, monkeypatch)

    with pytest.raises(scraping_sunat.SesionSolError):
        scraping_sunat._login_con_reintentos(pagina, "20", "usr", "clave", lambda _m: None)

    assert intentos["n"] == scraping_sunat.INTENTOS_LOGIN


def test_no_reintenta_credenciales_rechazadas(pagina, monkeypatch, tmp_path):
    """Reintentar una clave mal guardada acaba bloqueando el usuario en SOL."""
    monkeypatch.setattr(scraping_sunat, "LOG_DIR", tmp_path)
    intentos = _login_que_falla(
        99, monkeypatch, scraping_sunat.CredencialesSolError("clave incorrecta")
    )

    with pytest.raises(scraping_sunat.CredencialesSolError):
        scraping_sunat._login_con_reintentos(pagina, "20", "usr", "clave", lambda _m: None)

    assert intentos["n"] == 1
    assert pagina.esperas_ms == []


def test_guarda_evidencia_de_cada_fallo(pagina, monkeypatch, tmp_path):
    """Sin captura ni URL, un rechazo no deja nada que mirar después."""
    monkeypatch.setattr(scraping_sunat, "LOG_DIR", tmp_path)
    _login_que_falla(1, monkeypatch)
    mensajes: list[str] = []

    scraping_sunat._login_con_reintentos(pagina, "20", "usr", "clave", mensajes.append)

    evidencia = next(m for m in mensajes if m.startswith("Evidencia"))
    assert "api-seguridad.sunat.gob.pe" in evidencia
    assert "typeof_login=function" in evidencia
    assert "typeof_ejecuta=undefined" in evidencia
    assert len(pagina.capturas) == 1


def test_la_evidencia_no_puede_tapar_el_fallo(pagina, monkeypatch, tmp_path):
    """Si la captura revienta, el error que importa sigue siendo el del login."""
    monkeypatch.setattr(scraping_sunat, "LOG_DIR", tmp_path)

    def revienta(*_a, **_k):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(pagina, "screenshot", revienta)
    _login_que_falla(99, monkeypatch)

    with pytest.raises(scraping_sunat.SesionSolError):
        scraping_sunat._login_con_reintentos(pagina, "20", "usr", "clave", lambda _m: None)
