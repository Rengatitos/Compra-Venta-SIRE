"""El recuadro «LEYENDA» del popup es la glosa real de muchas FE recibidas: en
una comisión bancaria el ítem dice sólo «CONCEPTO DE PAGO:COMISION» y es la
leyenda la que cuenta que fue por «TARJETA DE DEBITO». Antes ni se leía."""

from __future__ import annotations

from app.services.scraping_sunat import _parsear_leyenda

# Tal cual lo devuelve `_JS_LEER_LEYENDA` para FN01-49860263 (BCP).
FILAS_BCP = [
    "-TARJETA DE DEBITO",
    "-Credimas Negocio Juridica",
    "-100 *****850 0 **",
    "-2026-08-17",
    "-TD",
    "-SAT",
    "-",
]


def test_quita_la_vineta_y_las_lineas_vacias():
    assert _parsear_leyenda(FILAS_BCP) == [
        "TARJETA DE DEBITO",
        "Credimas Negocio Juridica",
        "100 *****850 0 **",
        "2026-08-17",
        "TD",
        "SAT",
    ]


def test_colapsa_los_blancos_del_html():
    (linea,) = _parsear_leyenda(["  -\tSON  DIEZ\n CON 00/100 SOLES  "])

    assert linea == "SON DIEZ CON 00/100 SOLES"


def test_no_repite_ni_incluye_el_rotulo():
    assert _parsear_leyenda(["LEYENDA", "-SAT", "- SAT", "Leyenda"]) == ["SAT"]


def test_sin_recuadro_devuelve_lista_vacia():
    assert _parsear_leyenda([]) == []
    assert _parsear_leyenda([None, "", "   "]) == []


def test_el_js_no_lleva_escapes():
    """Un escape en el JS no sobrevive al import y rompe la lectura entera.

    `_JS_LEER_LEYENDA` viaja como cadena de Python, así que un `\n` escrito
    dentro se convierte en un salto real y el navegador recibe la función
    partida por la mitad: `SyntaxError`, ninguna leyenda y un aviso por
    comprobante en el log. Pasó dos veces, incluso en el comentario que lo
    advertía, así que aquí queda vigilado.
    """
    from app.services.scraping_sunat import _JS_LEER_LEYENDA

    assert "\\" not in _JS_LEER_LEYENDA
