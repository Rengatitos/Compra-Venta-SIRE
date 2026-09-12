import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domain.comprobante import Libro
from app.services import scraping_sunat as scraper
from app.services.sunat import see_sol


@pytest.mark.parametrize('libro,tipo,modificado,esperado', [
    (Libro.VENTAS, '01', None, (False, '10')),
    (Libro.COMPRAS, '01', None, (False, '11')),
    (Libro.VENTAS, '07', None, (False, '13')),
    (Libro.COMPRAS, '07', None, (False, '14')),
    (Libro.VENTAS, '08', None, (False, '15')),
    (Libro.COMPRAS, '08', None, (False, '16')),
    (Libro.VENTAS, '03', None, (True, '17')),
    (Libro.COMPRAS, '03', None, (True, '18')),
    (Libro.VENTAS, '07', '03', (True, '20')),
    (Libro.VENTAS, '08', '03', (True, '22')),
])
def test_bandejas(libro, tipo, modificado, esperado):
    fac = {'tipo_cp': tipo, 'extra': {
        'documentos_modificados': [{'codTipoCDP': modificado}] if modificado else []}}
    assert scraper._ruta_see_sol(fac, libro) == esperado


def listado(filas):
    return '<textarea>' + json.dumps({'codeError': 0, 'data': json.dumps(filas)}) + '</textarea>'


def test_indice_seleccionado_por_identidad_completa():
    filas = see_sol.leer_consulta(listado([
        {'id': '0', 'nroRucEmisor': 'otro', 'codCpe': '01',
         'nroSerie': 'E001', 'nroFactura': '359'},
        {'id': '7', 'nroRucEmisor': 'proveedor', 'codCpe': '01',
         'tipoCPE': '10', 'nroSerie': 'E001', 'nroFactura': '359'},
    ]))
    assert see_sol.buscar_fila(filas, ruc='proveedor', tipo='01',
                              serie='E001', numero='000359') == '7'
    assert see_sol.buscar_fila(filas, ruc='proveedor', tipo='07',
                              serie='E001', numero='359') is None


@pytest.mark.parametrize('html', ['<html>Login</html>', '<textarea>{}</textarea>',
                                '<textarea>{"codeError":1}</textarea>'])
def test_respuestas_invalidas_no_son_listados_vacios(html):
    with pytest.raises(ValueError):
        see_sol.leer_consulta(html)


def test_tablas_factura_boleta_y_totales():
    detalles = see_sol.leer_detalles([
        [['Cantidad', 'Unidad Medida', 'Descripción', 'Valor Unitario'],
         ['1.00', 'UNIDAD', 'SERVICIO CONTABLE', '1750.00']],
        [['Cantidad', 'Unidad Medida', 'Descripción', 'Valor Unitario(*)',
          'Descuento(*)', 'Importe de Venta(**)'],
         ['1.00', 'UNIDAD', 'VENTA DE LOTE', '47000.00', '0.00', '47000.00']],
        [['Total', '47000.00']],
    ])
    assert [d['descripcion'] for d in detalles] == ['SERVICIO CONTABLE', 'VENTA DE LOTE']
    assert detalles[0]['codigo'] == ''
    assert detalles[1]['valor_venta'] == '47000.00'
    assert detalles[1]['precio_unitario'] == ''


def test_consulta_antes_de_imprimir_y_cierra_popup(monkeypatch):
    abrir = MagicMock()
    monkeypatch.setattr(scraper, '_abrir_modulo_see_sol', abrir)
    context = MagicMock()
    context.request.get.return_value.text.return_value = listado([
        {'id': '2', 'nroRucEmisor': 'proveedor', 'codCpe': '01',
         'nroSerie': 'E001', 'nroFactura': '359'}])
    popup = context.new_page.return_value
    popup.evaluate.return_value = [[
        ['Cantidad', 'Unidad Medida', 'Descripción', 'Valor Unitario'],
        ['1', 'UNIDAD', 'Servicio', '10'],
    ]]
    detalles, pdf, xml = scraper._consultar_uno_see_sol(
        MagicMock(), context, MagicMock(),
        {'tipo_cp': '01', 'serie': 'E001', 'numero': '359',
         'documento_contraparte': 'proveedor', 'fecha_emision': date(2024, 2, 10)},
        Libro.COMPRAS, 'empresa', 1000, MagicMock())
    parametros = context.request.get.call_args.kwargs['params']
    assert parametros['fec_hasta'] == '29/02/2024'
    assert parametros['tipoConsulta'] == '11'
    assert 'rowIndex=2' in popup.goto.call_args.args[0]
    assert detalles[0]['descripcion'] == 'Servicio'
    assert pdf is xml is None
    popup.close.assert_called_once()
