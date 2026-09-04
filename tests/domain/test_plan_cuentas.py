"""El Excel de Contasis dibuja la jerarquía con la sangría, no con una columna
de nivel, y firma el archivo con una fila que no es una cuenta. Los dos
detalles se los come un lector escrito de corrido, y los dos rompen el maestro
de forma silenciosa: el primero deja la mitad de las cuentas sin código, el
segundo mete una cuenta de 98 caracteres."""

from __future__ import annotations

import pytest

from app.domain.plan_cuentas import Cuenta, es_codigo, localizar_columnas, parsear

# La cabecera real: «CUENTA» abre tres columnas de sangría sin rótulo propio, y
# «DESCRIPCION» cierra el bloque.
CABECERA = (
    None,
    "CUENTA",
    None,
    None,
    "DESCRIPCION",
    "C.BAL",
    "A.DEBE",
    "A.HABER",
    "TIPO",
    "ANALISIS",
    "CENTRO DE COSTOS",
)

# Filas tal como salen del archivo, con el relleno a ancho fijo incluido.
ELEMENTO = (
    None, "01        ", None, None, "BIENES Y VALORES ENTREGADOS   ",
    "    ", "  ", "  ", "Orden", None, None,
)
CUENTA = (
    None, None, "011       ", None, "BIENES EN PRÉSTAMO, CUSTODIA  ",
    "    ", "  ", "  ", "Orden", None, None,
)
SUBCUENTA = (
    None, None, None, "0111      ", "BIENES EN PRESTAMO - Entregados", "    ", "  ", "  ",
    "Orden", "Documentos", "Sin centro de Costos",
)
# Con lo que Contasis pone al final del archivo, en la columna del código.
FIRMA_TEXTO = (
    "Generado automáticamente por GESTIÓN CONTABLE FINANCIERO PREMIUM 26.00 "
    "- NewContaSis el 26/06/2026"
)
FIRMA = (None, FIRMA_TEXTO, None, None, None, None, None, None, None, None, None)


class TestCabecera:
    def test_las_columnas_del_codigo_son_las_de_la_sangria(self):
        columnas = localizar_columnas(CABECERA)

        assert columnas is not None
        assert columnas.codigo == (1, 2, 3)
        assert columnas.descripcion == 4
        assert columnas.tipo == 8
        assert columnas.analisis == 9
        assert columnas.centro_costos == 10

    def test_una_fila_de_datos_no_es_la_cabecera(self):
        assert localizar_columnas(SUBCUENTA) is None

    def test_se_localiza_aunque_las_columnas_se_muevan(self):
        # El archivo lo exporta Contasis y las columnas se han movido entre
        # versiones, así que se busca por texto y no por posición.
        movida = (None, None, "CUENTA", None, "DESCRIPCION", "TIPO")
        columnas = localizar_columnas(movida)

        assert columnas is not None
        assert columnas.codigo == (2, 3)
        assert columnas.descripcion == 4
        assert columnas.tipo == 5

    def test_sin_cabecera_se_avisa_en_vez_de_devolver_vacio(self):
        # Un maestro vacío y un archivo equivocado son problemas distintos y
        # el usuario tiene que poder distinguirlos.
        with pytest.raises(ValueError, match="cabeceras"):
            parsear([SUBCUENTA, SUBCUENTA])


class TestCodigo:
    def test_un_codigo_de_cuenta_es_valido(self):
        assert es_codigo("01")
        assert es_codigo("0111")
        assert es_codigo("104010101")

    def test_el_relleno_a_ancho_fijo_no_estorba(self):
        assert es_codigo("01        ")

    def test_una_frase_no_es_un_codigo(self):
        assert not es_codigo("BIENES EN PRESTAMO")
        assert not es_codigo(FIRMA_TEXTO)

    def test_una_celda_vacia_no_es_un_codigo(self):
        assert not es_codigo(None)
        assert not es_codigo("   ")


class TestParseo:
    def test_el_nivel_sale_de_la_columna_del_codigo(self):
        # Es lo único que codifica la jerarquía: no hay columna de nivel.
        cuentas = parsear([CABECERA, ELEMENTO, CUENTA, SUBCUENTA])

        assert [(c.cuenta, c.nivel) for c in cuentas] == [
            ("01", 1),
            ("011", 2),
            ("0111", 3),
        ]

    def test_recorta_el_relleno_de_todas_las_celdas(self):
        # Sin recortar, nada casa después: ni el índice único, ni el buscador,
        # ni el cruce con la clasificación de la IA.
        cuenta = parsear([CABECERA, SUBCUENTA])[0]

        assert cuenta == Cuenta(
            cuenta="0111",
            descripcion="BIENES EN PRESTAMO - Entregados",
            tipo="Orden",
            analisis="Documentos",
            centro_costos="Sin centro de Costos",
            nivel=3,
        )

    def test_descarta_la_firma_de_contasis(self):
        cuentas = parsear([CABECERA, ELEMENTO, FIRMA])

        assert [c.cuenta for c in cuentas] == ["01"]

    def test_descarta_filas_en_blanco(self):
        cuentas = parsear([CABECERA, ELEMENTO, (None,) * 11, ELEMENTO])

        assert [c.cuenta for c in cuentas] == ["01"]

    def test_conserva_las_tildes(self):
        # El archivo trae «PRÉSTAMO» y «Función» en latin-1 legítimo; una
        # descripción mutilada llega tal cual a la glosa del auditor.
        cuenta = parsear([CABECERA, CUENTA])[0]

        assert "PRÉSTAMO" in cuenta.descripcion

    def test_un_codigo_repetido_se_queda_con_la_primera_aparicion(self):
        # La colección tiene índice único por (empresa, cuenta): un duplicado
        # en el archivo tumbaría la carga entera al insertar.
        repetida = (
            None, None, None, "0111      ", "OTRA DESCRIPCION",
            None, None, None, "Activo", None, None,
        )
        cuentas = parsear([CABECERA, SUBCUENTA, repetida])

        assert [c.descripcion for c in cuentas] == ["BIENES EN PRESTAMO - Entregados"]

    def test_las_columnas_opcionales_pueden_faltar(self):
        minima = (None, "CUENTA", "DESCRIPCION")
        cuentas = parsear([minima, (None, "01", "UN ELEMENTO")])

        assert cuentas == [Cuenta(cuenta="01", descripcion="UN ELEMENTO", nivel=1)]

    def test_una_fila_mas_corta_que_la_cabecera_no_revienta(self):
        cuentas = parsear([CABECERA, (None, None, None, "0111", "SOLO HASTA AQUI")])

        assert cuentas == [Cuenta(cuenta="0111", descripcion="SOLO HASTA AQUI", nivel=3)]
