"""Cada bandeja valida el formato de sus criterios: la serie de `FE Recibidas`
sólo acepta `F###` y la de `BVE Emitidas - OSE` sólo `B###`. Con un campo
inválido el botón Buscar no envía nada, y eso llegaba al log como «SUNAT no lo
tiene»: lo contrario de lo que pasaba. Estos tests fijan que se distinga."""

from __future__ import annotations

from app.services import scraping_sunat
from app.services.scraping_sunat import (
    SEL_FEC_DESDE,
    SEL_NUMERO,
    SEL_RUC,
    SEL_SERIE,
)


class CampoFalso:
    def __init__(self, invalido: bool, existe: bool = True) -> None:
        self._invalido = invalido
        self._existe = existe

    @property
    def first(self) -> CampoFalso:
        return self

    def count(self) -> int:
        return 1 if self._existe else 0

    def get_attribute(self, nombre: str):
        if nombre != "aria-invalid":
            return None
        return "true" if self._invalido else "false"


class IframeFalso:
    def __init__(self, invalidos: dict[str, bool], ilegibles: tuple[str, ...] = ()) -> None:
        self._invalidos = invalidos
        self._ilegibles = ilegibles

    def locator(self, selector: str) -> CampoFalso:
        if selector in self._ilegibles:
            raise RuntimeError("el campo se desprendió del DOM")
        return CampoFalso(self._invalidos.get(selector, False))


def test_detecta_la_serie_que_la_bandeja_no_admite():
    iframe = IframeFalso({SEL_SERIE: True})
    escritos = [
        (SEL_RUC, "el RUC", ""),
        (SEL_SERIE, "la serie", "EB01"),
        (SEL_NUMERO, "el número", "187"),
    ]

    assert scraping_sunat._criterios_rechazados(iframe, escritos) == ["la serie='EB01'"]


def test_un_criterio_vacio_no_cuenta_como_rechazado():
    """El RUC del receptor se deja vacío a propósito en las boletas a DNI, y el
    portal lo marca inválido sin que eso impida buscar."""
    iframe = IframeFalso({SEL_RUC: True})
    escritos = [
        (SEL_RUC, "el RUC", ""),
        (SEL_SERIE, "la serie", "B001"),
    ]

    assert scraping_sunat._criterios_rechazados(iframe, escritos) == []


def test_sin_criterios_invalidos_no_hay_nada_que_avisar():
    iframe = IframeFalso({})
    escritos = [
        (SEL_SERIE, "la serie", "F001"),
        (SEL_NUMERO, "el número", "43318"),
        (SEL_FEC_DESDE, "la fecha desde", "14/07/2026"),
    ]

    assert scraping_sunat._criterios_rechazados(iframe, escritos) == []


def test_un_campo_ilegible_no_bloquea_la_busqueda():
    """Si no se puede leer la validación se sigue como antes: que decida el
    portal. Perder la comprobación no puede costar el comprobante."""
    iframe = IframeFalso({SEL_SERIE: True}, ilegibles=(SEL_SERIE,))
    escritos = [(SEL_SERIE, "la serie", "EB01")]

    assert scraping_sunat._criterios_rechazados(iframe, escritos) == []


def test_el_mensaje_dice_la_bandeja_y_el_criterio():
    """El log tiene que permitir diagnosticar sin volver a abrir el navegador."""
    rechazo = scraping_sunat.CriterioRechazado(
        "EB01-187", "BVE Emitidas - OSE", ["la serie='EB01'"]
    )

    assert "BVE Emitidas - OSE" in str(rechazo)
    assert "EB01" in str(rechazo)
    assert rechazo.serie_numero == "EB01-187"
