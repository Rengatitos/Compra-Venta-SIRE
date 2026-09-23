"""Ficha RUC pública de SUNAT (Consulta RUC, e-consultaruc.sunat.gob.pe).

De ahí salen las actividades económicas (CIIU) de un contribuyente, que el
clasificador contable usa como contexto: una compra a un proveedor de
«actividades de mensajería» se interpreta distinto que la misma descripción a
un ferretero. También trae los comprobantes que tiene autorizados y su sistema
de emisión.

Dos mitades separadas a propósito:

- `parsear_ficha` es lógica pura sobre el HTML del resultado, así que se
  prueba contra una página real guardada sin abrir ningún navegador.
- `consultar_fichas` abre Chromium con Playwright, escribe el RUC en el
  formulario y pulsa «Buscar». El formulario lleva un `token` que genera la
  propia página, por eso no se replica el POST a mano. El contexto se abre con
  el mismo user-agent que el scraper del portal SOL: con el de Chromium
  headless la página se queda en la verificación del navegador.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser

from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

URL_CONSULTA = "https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/FrameCriterioBusquedaWeb.jsp"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
SEL_RUC = "#txtRuc"
SEL_BUSCAR = "#btnAceptar"

# «Principal    - 4759 - VENTA AL POR MENOR…» / «Secundaria 1 - 5320  - …».
# Algunas fichas antiguas escriben «CIIU 4759»; se admite.
_ACTIVIDAD = re.compile(
    r"^(?P<tipo>principal|secundaria)\s*(?P<orden>\d*)\s*-\s*(?:ciiu\s*)?"
    r"(?P<ciiu>\d{4,5})\s*-\s*(?P<descripcion>.+)$",
    re.IGNORECASE,
)
_ESPACIOS = re.compile(r"\s+")


class FichaNoEncontrada(LookupError):
    """SUNAT no devolvió la ficha: RUC inexistente o página inesperada."""


class ActividadRuc(BaseModel):
    tipo: str  # PRINCIPAL / SECUNDARIA
    orden: int = 0  # 0 para la principal; 1, 2… para las secundarias
    ciiu: str
    descripcion: str


class FichaRuc(BaseModel):
    ruc: str
    razon_social: str = ""
    tipo_contribuyente: str = ""
    nombre_comercial: str = ""
    fecha_inscripcion: str = ""
    fecha_inicio_actividades: str = ""
    estado: str = ""
    condicion: str = ""
    domicilio_fiscal: str = ""
    sistema_emision: str = ""
    actividad_comercio_exterior: str = ""
    sistema_contabilidad: str = ""
    actividades_economicas: list[ActividadRuc] = Field(default_factory=list)
    comprobantes_autorizados: list[str] = Field(default_factory=list)
    sistema_emision_electronica: list[str] = Field(default_factory=list)
    emisor_electronico_desde: str = ""
    comprobantes_electronicos: list[str] = Field(default_factory=list)
    afiliado_ple_desde: str = ""
    padrones: list[str] = Field(default_factory=list)
    consultado_en: datetime | None = None


def _limpio(texto: str) -> str:
    return _ESPACIOS.sub(" ", texto or "").strip()


class _Lector(HTMLParser):
    """Aplana el panel de resultados a una secuencia `(etiqueta, texto)`.

    Cada dato de la ficha es un `<h4>` que termina en «:» seguido de su valor,
    que va en un `<p>`, en filas `<td>` o —en el caso del RUC— en otro `<h4>`.
    Leer en orden y agrupar por rótulo aguanta los cambios de columnas de
    Bootstrap que la página ha tenido con los años.
    """

    _BLOQUES = {"h4", "p", "td"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.piezas: list[tuple[str, str]] = []
        self._abierta: str | None = None
        self._texto: list[str] = []
        # Una entrada por `<div>` abierto: si está dentro del panel de
        # resultados (`list-group`). Fuera de él sólo hay botones y el pie
        # «© SUNAT», que se colaría en el último campo leído.
        self._divs: list[bool] = []

    def _en_panel(self) -> bool:
        return any(self._divs)

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            clases = (dict(attrs).get("class") or "").split()
            self._divs.append("list-group" in clases or "list-group-item" in clases)
        elif tag in self._BLOQUES and self._en_panel():
            self._abierta = tag
            self._texto = []

    def handle_endtag(self, tag):
        if tag == "div" and self._divs:
            self._divs.pop()
        elif tag == self._abierta:
            texto = _limpio("".join(self._texto))
            if texto:
                self.piezas.append((tag, texto))
            self._abierta = None

    def handle_data(self, data):
        if self._abierta:
            self._texto.append(data)


def _campos(html: str) -> dict[str, list[str]]:
    lector = _Lector()
    lector.feed(html)
    campos: dict[str, list[str]] = {}
    rotulo: str | None = None
    for etiqueta, texto in lector.piezas:
        if etiqueta == "h4" and texto.endswith(":"):
            rotulo = texto[:-1].strip().upper()
            campos.setdefault(rotulo, [])
        elif rotulo is not None:
            campos[rotulo].append(texto)
    return campos


def _uno(campos: dict[str, list[str]], *rotulos: str) -> str:
    for rotulo in rotulos:
        valores = campos.get(rotulo)
        if valores:
            valor = valores[0]
            return "" if valor == "-" else valor
    return ""


def _lista(campos: dict[str, list[str]], rotulo: str) -> list[str]:
    return [v for v in campos.get(rotulo, []) if v not in ("-", "NINGUNO")]


def parsear_actividad(linea: str) -> ActividadRuc | None:
    coincide = _ACTIVIDAD.match(_limpio(linea))
    if not coincide:
        return None
    return ActividadRuc(
        tipo=coincide["tipo"].upper(),
        orden=int(coincide["orden"] or 0),
        ciiu=coincide["ciiu"],
        descripcion=_limpio(coincide["descripcion"]),
    )


def parsear_ficha(html: str) -> FichaRuc:
    campos = _campos(html)
    numero = _uno(campos, "NÚMERO DE RUC")
    if not numero:
        raise FichaNoEncontrada("La respuesta de SUNAT no trae la ficha del RUC")
    ruc, _, razon_social = numero.partition(" - ")

    actividades = [
        actividad
        for linea in campos.get("ACTIVIDAD(ES) ECONÓMICA(S)", [])
        if (actividad := parsear_actividad(linea)) is not None
    ]
    electronicos = _uno(campos, "COMPROBANTES ELECTRÓNICOS")
    return FichaRuc(
        ruc=ruc.strip(),
        razon_social=razon_social.strip(),
        tipo_contribuyente=_uno(campos, "TIPO CONTRIBUYENTE"),
        nombre_comercial=_uno(campos, "NOMBRE COMERCIAL"),
        fecha_inscripcion=_uno(campos, "FECHA DE INSCRIPCIÓN"),
        fecha_inicio_actividades=_uno(campos, "FECHA DE INICIO DE ACTIVIDADES"),
        estado=_uno(campos, "ESTADO DEL CONTRIBUYENTE"),
        condicion=_uno(campos, "CONDICIÓN DEL CONTRIBUYENTE"),
        domicilio_fiscal=_uno(campos, "DOMICILIO FISCAL"),
        sistema_emision=_uno(campos, "SISTEMA EMISIÓN DE COMPROBANTE"),
        actividad_comercio_exterior=_uno(campos, "ACTIVIDAD COMERCIO EXTERIOR"),
        sistema_contabilidad=_uno(campos, "SISTEMA CONTABILIDAD"),
        actividades_economicas=actividades,
        comprobantes_autorizados=_lista(
            campos, "COMPROBANTES DE PAGO C/AUT. DE IMPRESIÓN (F. 806 U 816)"
        ),
        sistema_emision_electronica=_lista(campos, "SISTEMA DE EMISIÓN ELECTRÓNICA"),
        emisor_electronico_desde=_uno(campos, "EMISOR ELECTRÓNICO DESDE"),
        comprobantes_electronicos=[
            _limpio(c) for c in electronicos.split(",") if _limpio(c)
        ],
        afiliado_ple_desde=_uno(campos, "AFILIADO AL PLE DESDE"),
        padrones=_lista(campos, "PADRONES"),
    )


def es_ruc(valor: str) -> bool:
    valor = (valor or "").strip()
    return len(valor) == 11 and valor.isdigit() and valor[:2] in {"10", "15", "17", "20"}


def consultar_fichas(rucs: list[str]) -> dict[str, FichaRuc | Exception]:
    """Consulta varias fichas con un solo navegador. Bloquea: llamarlo en un hilo.

    Un fallo en un RUC no corta los demás: queda como excepción en el
    resultado para que quien llama decida.
    """
    from playwright.sync_api import sync_playwright

    resultado: dict[str, FichaRuc | Exception] = {}
    timeout = settings.SUNAT_SCRAPER_TIMEOUT_MS * 2
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.SUNAT_SCRAPER_HEADLESS)
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="es-PE")
            page = context.new_page()
            for ruc in rucs:
                try:
                    page.goto(URL_CONSULTA, wait_until="domcontentloaded", timeout=timeout)
                    page.locator(SEL_RUC).fill(ruc, timeout=timeout)
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout):
                        page.locator(SEL_BUSCAR).click()
                    ficha = parsear_ficha(page.content())
                    ficha.consultado_en = datetime.now(UTC)
                    resultado[ruc] = ficha
                except Exception as exc:
                    logger.warning("No se pudo consultar la ficha RUC %s: %s", ruc, exc)
                    resultado[ruc] = exc
        finally:
            browser.close()
    return resultado


def consultar_ficha(ruc: str) -> FichaRuc:
    resultado = consultar_fichas([ruc])[ruc]
    if isinstance(resultado, Exception):
        raise resultado
    return resultado
