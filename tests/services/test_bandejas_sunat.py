"""El portal SOL separa una bandeja por tipo de documento, no una por libro.

Las opciones reales del combo «Tipo de consulta», leídas del portal:

    FE Emitidas · FE Recibidas · NC Emitidas · NC Recibidas · ND Emitidas
    ND Recibidas · BVE Emitidas - OSE · NC-BVE Emitidas - OSE
    ND-BVE Emitidas - OSE

Elegirla sólo por el libro mandaba todas las ventas a «FE Emitidas», y el
registro de ventas es casi todo boletas: en los periodos reales de prueba eran
28 de 28 y 4 de 4. Buscarlas entre las facturas no encuentra ninguna.
"""

from __future__ import annotations

from app.domain.comprobante import Libro
from app.services.scraping_sunat import bandeja


def _cp(tipo: str, **extra) -> dict:
    return {"tipo_cp": tipo, "serie": "F001", "numero": "1", **extra}


class TestBandejaPorTipoDeComprobante:
    def test_una_factura_recibida_es_una_compra(self):
        assert bandeja(_cp("01"), Libro.COMPRAS) == "FE Recibidas"

    def test_una_factura_emitida_es_una_venta(self):
        assert bandeja(_cp("01"), Libro.VENTAS) == "FE Emitidas"

    def test_una_boleta_emitida_va_a_la_bandeja_de_boletas(self):
        # El caso que estaba roto: es el grueso del registro de ventas.
        assert bandeja(_cp("03"), Libro.VENTAS) == "BVE Emitidas - OSE"

    def test_las_notas_tienen_su_propia_bandeja(self):
        assert bandeja(_cp("07"), Libro.COMPRAS) == "NC Recibidas"
        assert bandeja(_cp("08"), Libro.COMPRAS) == "ND Recibidas"
        assert bandeja(_cp("07"), Libro.VENTAS) == "NC Emitidas"
        assert bandeja(_cp("08"), Libro.VENTAS) == "ND Emitidas"

    def test_una_nota_sobre_boleta_va_a_la_bandeja_bve(self):
        # El tipo de la nota es 07 igual que cualquier otra; lo que la
        # distingue es el tipo del documento que corrige.
        nota = _cp("07", extra={"documentos_modificados": [{"codTipoCDP": "03"}]})
        assert bandeja(nota, Libro.VENTAS) == "NC-BVE Emitidas - OSE"

        debito = _cp("08", extra={"documentos_modificados": [{"codTipoCDP": "03"}]})
        assert bandeja(debito, Libro.VENTAS) == "ND-BVE Emitidas - OSE"

    def test_una_nota_sobre_factura_se_queda_en_la_bandeja_normal(self):
        nota = _cp("07", extra={"documentos_modificados": [{"codTipoCDP": "01"}]})
        assert bandeja(nota, Libro.VENTAS) == "NC Emitidas"

    def test_en_compras_no_se_usa_la_bandeja_bve(self):
        # El RCE no manda `documentoMod`, y las notas recibidas sobre boleta no
        # forman parte del registro de compras.
        nota = _cp("07", extra={"documentos_modificados": [{"codTipoCDP": "03"}]})
        assert bandeja(nota, Libro.COMPRAS) == "NC Recibidas"

    def test_un_tipo_desconocido_cae_en_la_bandeja_de_facturas(self):
        assert bandeja(_cp("50"), Libro.COMPRAS) == "FE Recibidas"
        assert bandeja(_cp(""), Libro.VENTAS) == "FE Emitidas"

    def test_el_tipo_se_normaliza_antes_de_buscar(self):
        # En Mongo el tipo ya viene normalizado a dos dígitos, pero un "3" o un
        # 3 entero no pueden mandar la boleta a la bandeja equivocada.
        assert bandeja(_cp("3"), Libro.VENTAS) == "BVE Emitidas - OSE"
        assert bandeja({"tipo_cp": 3}, Libro.VENTAS) == "BVE Emitidas - OSE"

    def test_sin_documentos_modificados_no_revienta(self):
        assert bandeja(_cp("07", extra={}), Libro.VENTAS) == "NC Emitidas"
        assert bandeja(_cp("07", extra={"documentos_modificados": []}), Libro.VENTAS) == (
            "NC Emitidas"
        )
        assert bandeja(_cp("07", extra={"documentos_modificados": ["basura"]}), Libro.VENTAS) == (
            "NC Emitidas"
        )
