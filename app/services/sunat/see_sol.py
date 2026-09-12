"""Lectura de las respuestas de consulta e impresión de SEE-SOL."""

import json
import re
import unicodedata
from html.parser import HTMLParser


class _Textarea(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dentro = False
        self.texto = []

    def handle_starttag(self, tag, attrs):
        if tag == "textarea":
            self.dentro = True

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.dentro = False

    def handle_data(self, data):
        if self.dentro:
            self.texto.append(data)


def leer_consulta(html: str) -> list[dict]:
    parser = _Textarea()
    parser.feed(html)
    try:
        respuesta = json.loads("".join(parser.texto))
        if str(respuesta.get("codeError")) != "0":
            raise ValueError("SEE-SOL rechazó la consulta")
        datos = respuesta["data"]
        filas = json.loads(datos) if isinstance(datos, str) else datos
        if not isinstance(filas, list) or any(not isinstance(f, dict) for f in filas):
            raise ValueError("Listado SEE-SOL inválido")
        return filas
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("SEE-SOL no devolvió un listado válido; revisa la sesión") from exc


def buscar_fila(filas, *, ruc, tipo, serie, numero):
    def numero_normalizado(valor):
        return str(valor).strip().lstrip("0") or "0"

    coincidencias = [f for f in filas if (
        str(f.get("nroRucEmisor", "")).strip() == ruc.strip()
        and str(f.get("codCpe", "")).zfill(2) == tipo
        and str(f.get("nroSerie", "")).strip().upper() == serie.strip().upper()
        and numero_normalizado(f.get("nroFactura", "")) == numero_normalizado(numero)
    )]
    if len(coincidencias) > 1:
        raise ValueError("SEE-SOL devolvió más de una coincidencia para el comprobante")
    if not coincidencias:
        return None
    indice = str(coincidencias[0].get("id", ""))
    if not indice.isdigit():
        raise ValueError("SEE-SOL devolvió un índice inválido")
    return indice


def leer_detalles(tablas: list[list[list[str]]]) -> list[dict]:
    campos = {
        "cantidad": "cantidad", "unidadmedida": "unidad_medida",
        "unidaddemedida": "unidad_medida", "descripcion": "descripcion",
        "codigo": "codigo", "valorunitario": "valor_unitario",
        "preciounitario": "precio_unitario", "importedeventa": "valor_venta",
        "valorventa": "valor_venta", "icbper": "icbper",
    }
    detalles = []
    for filas in tablas:
        columnas = {}
        for fila in filas:
            normalizadas = [re.sub(r"[^a-z]", "", unicodedata.normalize(
                "NFKD", c.lower()).encode("ascii", "ignore").decode()) for c in fila]
            if "cantidad" in normalizadas and "descripcion" in normalizadas:
                columnas = {i: campos[c] for i, c in enumerate(normalizadas) if c in campos}
                continue
            if not columnas:
                continue
            detalle = dict.fromkeys(campos.values(), "")
            for i, campo in columnas.items():
                if i < len(fila):
                    detalle[campo] = fila[i].strip()
            try:
                float(detalle["cantidad"].replace(",", ""))
            except ValueError:
                continue
            if detalle["descripcion"]:
                detalles.append(detalle)
    return detalles
