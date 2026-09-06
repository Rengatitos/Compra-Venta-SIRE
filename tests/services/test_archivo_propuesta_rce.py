import io
import zipfile
from decimal import Decimal

import pytest

from app.services.sunat.archivo_propuesta_rce import leer_zip
from app.services.sunat.auth import ErrorSunat

CABECERA = (
    "RUC,Periodo,Fecha de emisión,Fecha Vcto/Pago,Tipo CP/Doc.,Serie del CDP,"
    "Nro CP o Doc. Nro Inicial (Rango),Tipo Doc Identidad,Nro Doc Identidad,"
    "Apellidos Nombres/ Razón  Social,BI Gravado DG,IGV / IPM DG,BI Gravado DGNG,"
    "IGV / IPM DGNG,BI Gravado DNG,IGV / IPM DNG,Valor Adq. NG,ISC,ICBPER,"
    "Otros Trib/ Cargos,Total CP,Moneda,Tipo de Cambio,CAR SUNAT\n"
)


def _zip(fila: str) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr("propuesta.csv", CABECERA + fila)
    return salida.getvalue()


def _zip_con_delimitador(delimitador: str, fila: str) -> bytes:
    salida = io.BytesIO()
    contenido = CABECERA.replace(",", delimitador) + fila
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr("propuesta.csv", contenido)
    return salida.getvalue()


def test_importa_moneda_tipo_cambio_y_todos_los_montos():
    fila = (
        "20610202251,202608,27/08/2026,,01,E001,359,6,20605744461,PROVEEDOR,"
        "33.00,5.93,0,0,0,0,85.19,1.00,0.20,0.30,125.62,USD,3.394,CAR1\n"
    )
    comprobante = leer_zip(_zip(fila), "20610202251", "202608")[0]
    assert comprobante.moneda == "USD"
    assert comprobante.tipo_cambio == Decimal("3.394")
    assert comprobante.base_imponible_dg == Decimal("33.00")
    assert comprobante.no_gravado == Decimal("85.19")
    assert comprobante.icbper == Decimal("0.20")
    assert comprobante.otros_tributos == Decimal("0.30")
    assert comprobante.total == Decimal("125.62")
    assert comprobante.extra["origen_archivo"] == "ticket_rce_csv"


def test_importa_csv_real_separado_por_punto_y_coma():
    fila = (
        "20610202251;202608;27/08/2026;;01;E001;359;6;20605744461;PROVEEDOR;"
        "33.00;5.93;0;0;0;0;0;0;0;0;38.93;USD;3.35;CAR1\n"
    )
    # SUNAT agrega al final una fila de totales sin RUC ni comprobante.
    fila += ";;;;;;;;;;32892.48;5904.34;;;;;;;;;;;;;\n"
    comprobantes = leer_zip(
        _zip_con_delimitador(";", fila), "20610202251", "202608"
    )
    comprobante = comprobantes[0]

    assert len(comprobantes) == 1
    assert comprobante.base_imponible_dg == Decimal("33.00")
    assert comprobante.igv_dg == Decimal("5.93")
    assert comprobante.tipo_cambio == Decimal("3.35")


def test_rechaza_un_zip_de_otro_ruc():
    fila = "20111111111,202608,, ,01,F001,1,,,,0,0,0,0,0,0,0,0,0,0,0,PEN,1,CAR\n"
    with pytest.raises(ErrorSunat, match="RUC"):
        leer_zip(_zip(fila), "20610202251", "202608")


def test_rechaza_un_archivo_que_no_es_zip():
    with pytest.raises(ErrorSunat, match="ZIP"):
        leer_zip(b"no es zip", "20610202251", "202608")
