"""El catálogo de estados por tipo es el acuerdo con el cliente del 12-sep-2026.

Cuatro tipos con glosa verificada, catorce que el scraper trata igual pero aún
sin casos reales, veintitrés que SUNAT no publica y doce por evaluar. Si un
código cambia de grupo, este test lo hace visible.
"""

from app.domain.catalogos import (
    SIN_DETALLE_POR_LIBRO,
    TIPO_COMPROBANTE,
    TIPOS_CON_DETALLE_SUNAT,
    TIPOS_EN_EVALUACION,
    TIPOS_SIN_DETALLE_SUNAT,
    describe_comprobante,
)

CON_GLOSA_VERIFICADA = {"01", "03", "07", "30"}
REQUIEREN_CASOS = {
    "08", "13", "14", "18", "19", "23", "29", "34", "35", "36", "42", "64", "87", "88",
}


def test_los_tres_grupos_no_se_pisan():
    assert not TIPOS_CON_DETALLE_SUNAT & TIPOS_SIN_DETALLE_SUNAT
    assert not TIPOS_CON_DETALLE_SUNAT & TIPOS_EN_EVALUACION
    assert not TIPOS_SIN_DETALLE_SUNAT & TIPOS_EN_EVALUACION


def test_tamanos_del_alcance():
    assert len(TIPOS_CON_DETALLE_SUNAT) == 18
    assert len(TIPOS_SIN_DETALLE_SUNAT) == 23
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
