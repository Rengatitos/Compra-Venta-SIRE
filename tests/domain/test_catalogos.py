"""El catálogo de estados por tipo es el acuerdo con el cliente del 12-sep-2026.

Tres tipos con glosa verificada, catorce que el scraper trata igual pero aún
sin casos reales, treinta y cinco que SUNAT no publica (los 23 del alcance, el
30 reclasificado con casos reales y once de los doce que estaban por evaluar)
y uno en evaluación (02, recibos por honorarios: SUNAT lo publica por otro
módulo). Si un código cambia de grupo, este test lo hace visible.
"""

from app.domain.catalogos import (
    SIN_DETALLE_POR_LIBRO,
    TIPO_COMPROBANTE,
    TIPOS_CON_DETALLE_SUNAT,
    TIPOS_EN_EVALUACION,
    TIPOS_SIN_DETALLE_SUNAT,
    describe_comprobante,
    sin_detalle_en_sunat,
)

CON_GLOSA_VERIFICADA = {"01", "03", "07"}
REQUIEREN_CASOS = {
    "08", "13", "14", "18", "19", "23", "29", "34", "35", "36", "42", "64", "87", "88",
}


def test_los_tres_grupos_no_se_pisan():
    assert not TIPOS_CON_DETALLE_SUNAT & TIPOS_SIN_DETALLE_SUNAT
    assert not TIPOS_CON_DETALLE_SUNAT & TIPOS_EN_EVALUACION
    assert not TIPOS_SIN_DETALLE_SUNAT & TIPOS_EN_EVALUACION


SIN_DETALLE_ALCANCE = {
    "00", "04", "05", "06", "11", "12", "15", "16", "17", "21", "24", "27",
    "28", "32", "37", "43", "44", "45", "48", "49", "55", "56", "89",
}
EVALUADOS_SIN_DETALLE = {"09", "10", "22", "25", "26", "31", "53", "91", "96", "97", "98"}


def test_tamanos_del_alcance():
    assert len(TIPOS_CON_DETALLE_SUNAT) == 17
    assert len(TIPOS_SIN_DETALLE_SUNAT) == 35
    assert TIPOS_EN_EVALUACION == {"02"}
    # El 30 salió del grupo con glosa: dos casos reales sin bandeja en SOL.
    assert TIPOS_SIN_DETALLE_SUNAT == SIN_DETALLE_ALCANCE | {"30"} | EVALUADOS_SIN_DETALLE
    # Los 12 del alcance quedaron todos resueltos.
    assert (EVALUADOS_SIN_DETALLE | TIPOS_EN_EVALUACION) == {
        "02", "09", "10", "22", "25", "26", "31", "53", "91", "96", "97", "98",
    }
    assert len(TIPOS_EN_EVALUACION) == 12


def test_con_detalle_cubre_verificados_y_pendientes_de_casos():
    assert CON_GLOSA_VERIFICADA <= TIPOS_CON_DETALLE_SUNAT
    assert REQUIEREN_CASOS <= TIPOS_CON_DETALLE_SUNAT
    assert TIPOS_CON_DETALLE_SUNAT == CON_GLOSA_VERIFICADA | REQUIEREN_CASOS


def test_todos_los_codigos_son_de_dos_caracteres():
    for grupo in (TIPOS_CON_DETALLE_SUNAT, TIPOS_SIN_DETALLE_SUNAT, TIPOS_EN_EVALUACION):
        assert all(len(codigo) == 2 for codigo in grupo)


def test_los_tipos_del_alcance_tienen_etiqueta():
    # 32, 37, 42 y 64 no venían del documento de Contasis y quedaban como
    # DESCONOCIDO en pantalla y en el Excel.
    sin_etiqueta = sorted(
        codigo
        for codigo in TIPOS_CON_DETALLE_SUNAT | TIPOS_SIN_DETALLE_SUNAT | TIPOS_EN_EVALUACION
        if codigo not in TIPO_COMPROBANTE
    )
    assert sin_etiqueta == []
    assert not describe_comprobante("64").startswith("DESCONOCIDO")


def test_excepciones_por_libro_declaradas_para_ambos_libros():
    assert set(SIN_DETALLE_POR_LIBRO) == {"compras", "ventas"}
    for tipos in SIN_DETALLE_POR_LIBRO.values():
        assert not tipos & TIPOS_SIN_DETALLE_SUNAT
    # El portal no tiene bandeja de boletas recibidas (ver
    # scripts/listar_bandejas_sol.py).
    assert SIN_DETALLE_POR_LIBRO["compras"] == {"03"}


def test_la_excepcion_por_libro_no_alcanza_a_las_series_see_sol():
    assert sin_detalle_en_sunat("03", "compras", "B001")
    assert sin_detalle_en_sunat("03", "compras", "b001")
    assert not sin_detalle_en_sunat("03", "compras", "EB01")
    assert not sin_detalle_en_sunat("03", "ventas", "B001")
    # Los tipos sin detalle lo son en cualquier libro y serie.
    assert sin_detalle_en_sunat("12", "ventas", "E001")
    assert not sin_detalle_en_sunat("01", "compras", "F001")
