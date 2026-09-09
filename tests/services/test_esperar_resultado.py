"""Tras pulsar Buscar hay tres desenlaces y confundirlos costaba comprobantes:
el enlace «Visualizar» aparece, el portal avisa de que no hay resultados, o
simplemente no responde a tiempo. Ese tercero se daba por «SUNAT no lo tiene»,
y así los bancos (BBVA, BCP), cuya consulta a veces pasa del plazo, quedaban sin
detalle ni PDF y sin reintento."""

from __future__ import annotations

import pytest

from app.services import scraping_sunat
from app.services.scraping_sunat import (
    SEL_VISUALIZAR,
    BusquedaSinRespuesta,
    ComprobanteNoEncontrado,
    _esperar_resultado,
)


class EnlaceFalso:
    def __init__(self, aparece_en_sondeo: int | None) -> None:
        self._aparece = aparece_en_sondeo
        self.consultas = 0

    @property
    def first(self) -> EnlaceFalso:
        return self

    def count(self) -> int:
        self.consultas += 1
        return 1 if self._aparece is not None and self.consultas > self._aparece else 0


class CuerpoFalso:
    def __init__(self, texto: str) -> None:
        self._texto = texto

    @property
    def first(self) -> CuerpoFalso:
        return self

    def inner_text(self, timeout: int = 0) -> str:
        return self._texto


class IframeFalso:
    def __init__(self, enlace: EnlaceFalso, texto: str = "Consulta de comprobantes") -> None:
        self.enlace = enlace
        self._texto = texto

    def locator(self, selector: str):
        if selector == SEL_VISUALIZAR:
            return self.enlace
        return CuerpoFalso(self._texto)


class RelojFalso:
    """Avanza un paso por cada `dormir`, para vencer plazos sin esperar."""

    def __init__(self) -> None:
        self.ahora = 0.0
        self.esperas: list[float] = []

    def __call__(self) -> float:
        return self.ahora

    def dormir(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.ahora += segundos


def _esperar(iframe, timeout_ms=1000, textos=("no se encontraron",)):
    reloj = RelojFalso()
    resultado = _esperar_resultado(
        iframe,
        "FN01-49860263",
        timeout_ms,
        textos_sin_resultados=textos,
        sondeo_ms=250,
        reloj=reloj,
        dormir=reloj.dormir,
    )
    return resultado, reloj


def test_devuelve_el_enlace_en_cuanto_aparece():
    enlace = EnlaceFalso(aparece_en_sondeo=2)
    iframe = IframeFalso(enlace)

    resultado, reloj = _esperar(iframe)

    assert resultado is enlace
    # Dos sondeos sin enlace, dos esperas; al tercero ya estaba.
    assert reloj.esperas == [0.25, 0.25]


def test_un_emisor_lento_no_se_da_por_inexistente():
    """El caso de los bancos: la búsqueda tarda pero el enlace llega."""
    enlace = EnlaceFalso(aparece_en_sondeo=30)
    iframe = IframeFalso(enlace)

    resultado, reloj = _esperar(iframe, timeout_ms=25000)

    assert resultado is enlace
    assert reloj.ahora == pytest.approx(7.5)


def test_el_aviso_de_sin_resultados_corta_al_instante():
    iframe = IframeFalso(EnlaceFalso(None), texto="No se encontraron registros para la consulta")

    with pytest.raises(ComprobanteNoEncontrado):
        _esperar(iframe, timeout_ms=25000)


def test_el_aviso_se_compara_sin_distinguir_mayusculas():
    iframe = IframeFalso(EnlaceFalso(None), texto="NO SE ENCONTRARON REGISTROS")

    with pytest.raises(ComprobanteNoEncontrado):
        _esperar(iframe)


def test_vencer_el_plazo_no_es_no_encontrado():
    iframe = IframeFalso(EnlaceFalso(None))

    with pytest.raises(BusquedaSinRespuesta) as excinfo:
        _esperar(iframe, timeout_ms=1000)

    assert not isinstance(excinfo.value, ComprobanteNoEncontrado)
    assert excinfo.value.serie_numero == "FN01-49860263"
    assert excinfo.value.timeout_ms == 1000
    assert "no respondió en 1 s" in str(excinfo.value)


def test_toma_los_textos_de_la_configuracion_por_defecto(monkeypatch):
    monkeypatch.setattr(
        scraping_sunat.settings, "SUNAT_TEXTOS_SIN_RESULTADOS", ("marcador propio",)
    )
    iframe = IframeFalso(EnlaceFalso(None), texto="… Marcador Propio …")
    reloj = RelojFalso()

    with pytest.raises(ComprobanteNoEncontrado):
        _esperar_resultado(iframe, "F001-1", 1000, reloj=reloj, dormir=reloj.dormir)


def test_un_iframe_a_medias_no_decide_nada():
    """Si el DOM se está recargando, `count()` revienta: se vuelve a mirar."""

    class EnlaceInestable(EnlaceFalso):
        def count(self) -> int:
            self.consultas += 1
            if self.consultas == 1:
                raise RuntimeError("frame detached")
            return 1

    enlace = EnlaceInestable(None)
    resultado, _ = _esperar(IframeFalso(enlace))

    assert resultado is enlace
