import pytest

from app.domain.carga_empresas import FilaCarga, Motivo, es_ruc_valido, validar_filas
from app.domain.empresa import normalizar_correos
from app.schemas.empresa import EmpresaCreate, EmpresaUpdate

RUC_A = "20610202251"
RUC_B = "20603391692"


def fila(numero=1, razon="EMPRESA", ruc=RUC_A, usuario="USU", password="clave"):
    return FilaCarga(numero, razon, ruc, usuario, password)


@pytest.mark.parametrize("ruc", [RUC_A, RUC_B, "10467793549", "20100070970"])
def test_ruc_con_digito_verificador_correcto(ruc):
    assert es_ruc_valido(ruc)


@pytest.mark.parametrize(
    "ruc",
    ["20123456789", "2061020225", "206102022510", "30610202251", "2061020225A", "", None],
)
def test_ruc_invalido(ruc):
    assert not es_ruc_valido(ruc)


@pytest.mark.parametrize(
    ("campos", "motivo"),
    [
        ({"razon": ""}, Motivo.FALTA_RAZON_SOCIAL),
        ({"ruc": ""}, Motivo.FALTA_RUC),
        ({"ruc": "20123456789"}, Motivo.RUC_INVALIDO),
        ({"usuario": ""}, Motivo.FALTA_USUARIO),
        ({"password": ""}, Motivo.FALTA_CONTRASENA),
    ],
)
def test_cada_campo_obligatorio_tiene_su_motivo(campos, motivo):
    [(_, motivos)] = validar_filas([fila(**campos)], set())
    assert motivos == [motivo]


def test_la_razon_social_es_opcional_en_el_alta_individual():
    [(_, motivos)] = validar_filas([fila(razon="")], set(), exigir_razon_social=False)
    assert motivos == []


def test_un_ruc_registrado_se_rechaza():
    [(_, motivos)] = validar_filas([fila()], {RUC_A})
    assert motivos == [Motivo.RUC_EXISTENTE]


def test_un_ruc_repetido_vale_solo_la_primera_vez():
    resultado = validar_filas([fila(1), fila(2), fila(3, ruc=RUC_B)], set())
    assert [motivos for _, motivos in resultado] == [[], [Motivo.DUPLICADO_EN_ARCHIVO], []]


def test_una_fila_incompleta_no_gasta_el_ruc():
    resultado = validar_filas([fila(1, password=""), fila(2)], set())
    assert [motivos for _, motivos in resultado] == [[Motivo.FALTA_CONTRASENA], []]


def test_la_contrasena_no_sale_en_el_repr_de_la_fila():
    assert "clave-secreta" not in repr(fila(password="clave-secreta"))


# --- Correos ----------------------------------------------------------------


def test_normaliza_mayusculas_espacios_y_duplicados():
    assert normalizar_correos([" A@B.pe ", "a@b.pe", "", "c@d.com"]) == ["a@b.pe", "c@d.com"]


@pytest.mark.parametrize("correo", ["sin-arroba", "a@b", "a b@c.pe", "@c.pe"])
def test_rechaza_lo_que_no_es_un_correo(correo):
    with pytest.raises(ValueError):
        normalizar_correos([correo])


def test_limita_la_cantidad_de_correos():
    with pytest.raises(ValueError):
        normalizar_correos([f"c{i}@x.pe" for i in range(11)])


def test_el_esquema_de_actualizacion_normaliza_y_respeta_el_nulo():
    assert EmpresaUpdate(correos_notificacion=["X@Y.PE"]).correos_notificacion == ["x@y.pe"]
    assert EmpresaUpdate(correos_notificacion=None).correos_notificacion is None
    assert "correos_notificacion" not in EmpresaUpdate().model_dump(exclude_unset=True)


def test_el_alta_exige_ruc_valido_y_usuario_y_clave():
    with pytest.raises(ValueError):
        EmpresaCreate(ruc="20123456789", usuario="U", password="p")
    with pytest.raises(ValueError):
        EmpresaCreate(ruc=RUC_A, usuario="", password="p")
    creada = EmpresaCreate(ruc=RUC_A, usuario=" USU ", password="p")
    assert creada.usuario == "USU"
