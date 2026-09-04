"""Carga del maestro desde el archivo subido.

El caso real vive en `source/`, que está en `.gitignore`, así que ese test se
salta cuando el archivo no está y el resto corre contra un libro construido en
memoria. Así la suite pasa en cualquier clon sin renunciar a comprobar el
archivo de verdad cuando está disponible.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services import plan_cuentas_service
from app.services.plan_cuentas_service import ExcelInvalido

ARCHIVO_REAL = Path(__file__).resolve().parents[2] / "source" / "CUENTAS CONTABLES.xlsx"

CABECERA = [None, "CUENTA", None, None, "DESCRIPCION", "TIPO", "ANALISIS", "CENTRO DE COSTOS"]


def _libro(filas, titulo="PLAN DE CUENTAS") -> bytes:
    wb = Workbook()
    hoja = wb.active
    hoja.title = titulo
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


FILAS = [
    CABECERA,
    [None, "01        ", None, None, "BIENES Y VALORES ENTREGADOS", "Orden", None, None],
    [None, None, "011       ", None, "BIENES EN PRÉSTAMO", "Orden", None, None],
    [
        None, None, None, "0111      ", "BIENES EN PRESTAMO",
        "Orden", "Documentos", "Sin centro de Costos",
    ],
]


class TestDesdeExcel:
    def test_lee_las_cuentas_con_su_nivel(self):
        cuentas = plan_cuentas_service.desde_excel(_libro(FILAS))

        assert [(c.cuenta, c.nivel) for c in cuentas] == [("01", 1), ("011", 2), ("0111", 3)]

    def test_encuentra_la_hoja_aunque_este_renombrada(self):
        # Un archivo que pasó por las manos de alguien puede traer la hoja con
        # otro nombre; las cabeceras son una señal más fiable que el rótulo.
        cuentas = plan_cuentas_service.desde_excel(_libro(FILAS, titulo="Hoja1"))

        assert len(cuentas) == 3

    def test_un_archivo_que_no_es_excel_se_rechaza_con_mensaje(self):
        # Tiene arreglo del lado del usuario, así que no puede salir como un
        # error interno: sale como 400 con el motivo.
        with pytest.raises(ExcelInvalido, match="Excel"):
            plan_cuentas_service.desde_excel(b"esto no es un xlsx")

    def test_un_archivo_vacio_se_rechaza(self):
        with pytest.raises(ExcelInvalido, match="vac"):
            plan_cuentas_service.desde_excel(b"")

    def test_un_excel_sin_las_columnas_esperadas_se_rechaza(self):
        otro = _libro([["FECHA", "IMPORTE"], ["01/01/2026", 100]], titulo="Ventas")

        with pytest.raises(ExcelInvalido, match="CUENTA"):
            plan_cuentas_service.desde_excel(otro)

    def test_una_hoja_sin_cuentas_utilizables_se_rechaza(self):
        with pytest.raises(ExcelInvalido, match="ninguna cuenta"):
            plan_cuentas_service.desde_excel(_libro([CABECERA]))


@pytest.mark.skipif(not ARCHIVO_REAL.is_file(), reason="source/ no está en este clon")
class TestArchivoReal:
    def test_lee_el_maestro_completo(self):
        cuentas = plan_cuentas_service.desde_excel(ARCHIVO_REAL.read_bytes())

        # 2.883 filas = cabecera + 2.881 cuentas + la firma de Contasis.
        assert len(cuentas) == 2881

    def test_ninguna_cuenta_queda_sin_codigo_ni_con_una_frase(self):
        cuentas = plan_cuentas_service.desde_excel(ARCHIVO_REAL.read_bytes())

        assert all(c.cuenta for c in cuentas)
        assert all(len(c.cuenta) <= 12 for c in cuentas)
        assert not any(" " in c.cuenta for c in cuentas)

    def test_los_tres_niveles_estan_representados(self):
        cuentas = plan_cuentas_service.desde_excel(ARCHIVO_REAL.read_bytes())
        por_nivel = {c.nivel for c in cuentas}

        assert por_nivel == {1, 2, 3}

    def test_conserva_las_tildes_del_archivo(self):
        cuentas = plan_cuentas_service.desde_excel(ARCHIVO_REAL.read_bytes())

        assert any("É" in c.descripcion for c in cuentas)
        assert any(c.tipo == "Función" for c in cuentas)
