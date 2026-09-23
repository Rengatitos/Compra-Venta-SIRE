"""Lectura de la ficha de la Consulta RUC de SUNAT.

`PAGINA` es el resultado real del portal recortado a su estructura (con los
datos personales cambiados): los rótulos en `<h4>`, los valores en `<p>`, en
filas `<td>` o, para el RUC, en otro `<h4>`, y el pie «© SUNAT» fuera del
panel, que no debe colarse en el último campo.
"""

from __future__ import annotations

import pytest

from app.services.clasificacion_service import construir_solicitud
from app.services.export_service import lineas_clasificacion
from app.services.ficha_ruc_service import actividades_de, contexto_de
from app.services.sunat.ficha_ruc import (
    FichaNoEncontrada,
    es_ruc,
    parsear_actividad,
    parsear_ficha,
)

PAGINA = """
<html><body>
<form name="selecXNroRuc"><input type="hidden" name="accion" value="consPorRazonSoc"></form>
<div class="container"><div class="row"><div class="col-md-12">
  <div><h1>Consulta RUC</h1></div>
  <div class="panel panel-primary">
    <div class="panel-heading">Resultado de la Búsqueda</div>
    <div class="list-group">
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">N&uacute;mero de RUC:</h4></div>
        <div class="col-sm-7"><h4 class="list-group-item-heading">10000000001 - PEREZ QUISPE JUAN</h4></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Tipo Contribuyente:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">PERSONA NATURAL CON NEGOCIO</p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Nombre Comercial:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">COMERCIAL PEREZ
          </p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-3"><h4 class="list-group-item-heading">Fecha de Inscripci&oacute;n:</h4></div>
        <div class="col-sm-3"><p class="list-group-item-text">16/12/1993</p></div>
        <div class="col-sm-3"><h4 class="list-group-item-heading">Fecha de Inicio de Actividades:</h4></div>
        <div class="col-sm-3"><p class="list-group-item-text">26/11/1993</p></div>
      </div></div>
      <div class="list-group-item list-group-item-success"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Estado del Contribuyente:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">ACTIVO

          </p></div>
      </div></div>
      <div class="list-group-item list-group-item-success"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Condici&oacute;n del Contribuyente:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">
              HABIDO
          </p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Domicilio Fiscal:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">-</p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-3"><h4 class="list-group-item-heading">Sistema Emisión de Comprobante:</h4></div>
        <div class="col-sm-3"><p class="list-group-item-text">MANUAL</p></div>
        <div class="col-sm-3"><h4 class="list-group-item-heading">Actividad Comercio Exterior:</h4></div>
        <div class="col-sm-3"><p class="list-group-item-text">SIN ACTIVIDAD</p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Actividad(es) Econ&oacute;mica(s):</h4></div>
        <div class="col-sm-7"><table class="table tblResultado"><tbody>
          <tr><td>Principal    - 4759 - VENTA AL POR MENOR DE APARATOS ELÉCTRICOS DE USO DOMÉSTICO, MUEBLES, EQU. DE ILUMINACIÓN Y OTROS ENSERES EN COM. ESPECIALIZADOS</td></tr>
          <!--SC003-2015 Inicio-->
          <tr><td>Secundaria 1 - 5320  - ACTIVIDADES DE MENSAJERÍA</td></tr>
        </tbody></table></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Comprobantes de Pago c/aut. de impresión (F. 806 u 816):</h4></div>
        <div class="col-sm-7"><table class="table tblResultado"><tbody>
          <tr><td>FACTURA</td></tr><tr><td>BOLETA DE VENTA</td></tr>
          <tr><td>NOTA DE CREDITO</td></tr><tr><td>GUIA DE REMISION - REMITENTE</td></tr>
        </tbody></table></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Sistema de Emisi&oacute;n Electr&oacute;nica:</h4></div>
        <div class="col-sm-7"><table class="table tblResultado"><tbody>
          <tr><td>FACTURA PORTAL                      DESDE 28/05/2024</td></tr>
          <tr><td>BOLETA PORTAL                       DESDE 02/08/2024</td></tr>
        </tbody></table></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Emisor electr&oacute;nico desde:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">26/08/2020</p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Comprobantes Electr&oacute;nicos:</h4></div>
        <div class="col-sm-7"><p class="list-group-item-text">FACTURA (desde 26/08/2020),BOLETA (desde 26/08/2020)</p></div>
      </div></div>
      <div class="list-group-item"><div class="row">
        <div class="col-sm-5"><h4 class="list-group-item-heading">Padrones:</h4></div>
        <div class="col-sm-7"><table class="table tblResultado"><tbody>
          <tr><td>NINGUNO</td></tr>
        </tbody></table></div>
      </div></div>
      <!-- <div class="list-group-item"><h4>Razón Social:</h4><p>eeee</p></div> -->
    </div>
    <div class="panel-footer text-center"><small>Fecha consulta: 22/09/2026 19:39</small></div>
  </div>
</div></div>
<footer class="footer text-center"><div class="col-md-12">
  <p><small>&copy; 1997 - 2026 SUNAT Derechos Reservados</small></p>
</div></footer>
</div>
</body></html>
"""


def test_lee_los_datos_de_la_ficha():
    ficha = parsear_ficha(PAGINA)

    assert ficha.ruc == "10000000001"
    assert ficha.razon_social == "PEREZ QUISPE JUAN"
    assert ficha.tipo_contribuyente == "PERSONA NATURAL CON NEGOCIO"
    assert ficha.nombre_comercial == "COMERCIAL PEREZ"
    assert (ficha.fecha_inscripcion, ficha.fecha_inicio_actividades) == ("16/12/1993", "26/11/1993")
    assert (ficha.estado, ficha.condicion) == ("ACTIVO", "HABIDO")
    assert ficha.domicilio_fiscal == ""  # «-» en la página
    assert ficha.sistema_emision == "MANUAL"
    assert ficha.actividad_comercio_exterior == "SIN ACTIVIDAD"
    assert ficha.comprobantes_autorizados == [
        "FACTURA", "BOLETA DE VENTA", "NOTA DE CREDITO", "GUIA DE REMISION - REMITENTE",
    ]
    assert ficha.sistema_emision_electronica == [
        "FACTURA PORTAL DESDE 28/05/2024", "BOLETA PORTAL DESDE 02/08/2024",
    ]
    assert ficha.emisor_electronico_desde == "26/08/2020"
    assert ficha.comprobantes_electronicos == [
        "FACTURA (desde 26/08/2020)", "BOLETA (desde 26/08/2020)",
    ]


def test_lee_las_actividades_economicas():
    actividades = parsear_ficha(PAGINA).actividades_economicas

    assert [(a.tipo, a.orden, a.ciiu) for a in actividades] == [
        ("PRINCIPAL", 0, "4759"), ("SECUNDARIA", 1, "5320"),
    ]
    assert actividades[1].descripcion == "ACTIVIDADES DE MENSAJERÍA"
    assert actividades[0].descripcion.startswith("VENTA AL POR MENOR DE APARATOS ELÉCTRICOS")


def test_el_pie_de_pagina_no_se_cuela_en_el_ultimo_campo():
    assert parsear_ficha(PAGINA).padrones == []


@pytest.mark.parametrize(
    ("linea", "esperado"),
    [
        ("Principal - CIIU 52322 - VENTA DE LIBROS", ("PRINCIPAL", 0, "52322")),
        ("Secundaria 2 - 4923 - TRANSPORTE DE CARGA", ("SECUNDARIA", 2, "4923")),
    ],
)
def test_formatos_de_actividad(linea, esperado):
    actividad = parsear_actividad(linea)
    assert (actividad.tipo, actividad.orden, actividad.ciiu) == esperado


def test_una_pagina_sin_ficha_es_un_ruc_no_encontrado():
    with pytest.raises(FichaNoEncontrada):
        parsear_ficha("<html><body><p>El número de RUC no es válido</p></body></html>")


def test_solo_los_ruc_validos_se_consultan():
    assert es_ruc("20610202251") and es_ruc("10000000001")
    assert not es_ruc("12345678") and not es_ruc("99999999999") and not es_ruc("")


def test_la_ficha_de_la_contraparte_llega_al_clasificador():
    ficha = parsear_ficha(PAGINA)
    assert actividades_de(ficha)[0] == {
        "tipo": "PRINCIPAL",
        "ciiu": "4759",
        "descripcion": ficha.actividades_economicas[0].descripcion,
        "origen": "sunat",
    }
    documento = {
        "_id": "x", "libro": "compras", "origen": "sire", "tipo_cp": "01",
        "serie": "F001", "numero": "9", "serie_numero": "F001-9",
        "documento_contraparte": "10000000001", "glosa": "Envio de documentos",
    }
    empresa = {"ruc": "20610202251", "actividades_economicas": [{"ciiu": "4663"}]}

    solicitud = construir_solicitud(documento, empresa, contexto_de(ficha))

    contraparte = solicitud.comprobante.contraparte
    assert [a.ciiu_v4 for a in contraparte.actividades_economicas] == ["4759", "5320"]
    assert "FACTURA" in contraparte.comprobantes_autorizados


def test_la_clasificacion_sale_legible_en_la_exportacion_individual():
    lineas = dict(lineas_clasificacion({"clasificacion_contable": {
        "cuenta_base": {"codigo": "6323094", "descripcion": "AUDITORIA - ADM"},
        "cuenta_total": {"codigo": "4212"},
        "confianza": 0.81,
        "requiere_revision": False,
    }}))
    assert lineas["Cuenta base"] == "6323094 - AUDITORIA - ADM"
    assert lineas["Cuenta total"] == "4212"
    assert lineas["Confianza"] == "81%"
    assert lineas["Requiere revisión"] == "No"
    assert lineas_clasificacion({}) == []
