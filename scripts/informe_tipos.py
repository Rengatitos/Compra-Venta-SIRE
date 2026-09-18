"""Informe por tipo de comprobante de un RUC y periodo: qué se obtuvo de SUNAT.

Es el entregable de las pruebas por tipo del cronograma: por cada tipo del
libro dice cuántos comprobantes hay, cuántos tienen detalle, PDF y glosa, en
qué estado de glosa quedan y por qué ruta del portal se consultan (bandeja o
SEE-SOL). Debajo lista cada comprobante sin glosa con la última línea que el
scraper dejó en `logs/automat_api.log` sobre él: es la evidencia de lo que
SUNAT respondió.

    uv run python scripts/informe_tipos.py --ruc 20603391692 --periodo 202602
    uv run python scripts/informe_tipos.py --ruc 20610202251 --periodo 202608 --salida ../Sire_Docs

Sólo lee: Mongo y el log. Escribe un Markdown en la carpeta indicada (por
defecto `logs/`).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.domain.catalogos import describe_comprobante, sin_detalle_en_sunat  # noqa: E402
from app.domain.comprobante import Libro, normalizar_tipo_cp  # noqa: E402
from app.services import scraping_sunat as sc  # noqa: E402
from app.services.glosa import ETIQUETA_ESTADO_GLOSA, estado_glosa, obtener_glosa  # noqa: E402

LOG = RAIZ / "logs" / "automat_api.log"


def _documentos(ruc: str, periodo: str) -> list[dict]:
    load_dotenv()
    cliente = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000)
    db = cliente[os.environ.get("MONGO_FACTURASDB_NAME", "Mod_Facturas")]
    empresa = db.empresas.find_one({"ruc": ruc})
    if not empresa:
        sys.exit(f"No hay empresa con RUC {ruc} en la base local")
    return list(db.comprobantes.find({"empresa_id": str(empresa["_id"]), "periodo": periodo}))


def _ruta(documento: dict, libro: Libro) -> str:
    serie = str(documento.get("serie") or "")
    if sin_detalle_en_sunat(normalizar_tipo_cp(documento.get("tipo_cp")), libro.value, serie):
        return "no se consulta: SUNAT no publica su detalle"
    if sc._es_serie_sol(serie):
        try:
            boleta, consulta = sc._ruta_see_sol(documento, libro)
        except ValueError as fallo:
            return f"SEE-SOL sin ruta ({fallo})"
        return f"SEE-SOL {'boletas' if boleta else 'facturas'} (tipoConsulta {consulta})"
    return f"bandeja «{sc.bandeja(documento, libro)}»"


def _ultimas_lineas_log() -> dict[str, str]:
    """Última línea del log que menciona cada serie-número."""
    if not LOG.exists():
        return {}
    ultimas: dict[str, str] = {}
    for linea in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        for token in linea.split():
            token = token.rstrip(":,;")
            if "-" in token and token.split("-")[0].isalnum() and token.split("-")[-1].isdigit():
                ultimas[token] = linea.strip()
    return ultimas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ruc", required=True)
    parser.add_argument("--periodo", required=True)
    parser.add_argument("--salida", default=str(RAIZ / "logs"), help="carpeta del Markdown")
    args = parser.parse_args()

    documentos = _documentos(args.ruc, args.periodo)
    log = _ultimas_lineas_log()

    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for documento in documentos:
        grupos[(str(documento.get("libro")), str(documento.get("tipo_cp")))].append(documento)

    lineas = [
        f"# Informe por tipo de comprobante — RUC {args.ruc}, periodo {args.periodo}",
        "",
        f"Fecha: {date.today().isoformat()}. Fuente: base local y `logs/automat_api.log`.",
        "",
        "| Libro | Tipo | Descripción | Cant. | Con detalle | Con PDF | Con glosa "
        "| Estado glosa | Ruta en SOL |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    sin_glosa: list[tuple[str, dict]] = []
    for (libro_txt, tipo), grupo in sorted(grupos.items()):
        libro = Libro(libro_txt)
        estados = defaultdict(int)
        for d in grupo:
            estados[ETIQUETA_ESTADO_GLOSA[estado_glosa(d)]] += 1
            if not obtener_glosa(d):
                sin_glosa.append((libro_txt, d))
        rutas = sorted({_ruta(d, libro) for d in grupo})
        lineas.append(
            f"| {libro_txt} | {tipo} | {describe_comprobante(tipo)} | {len(grupo)} | "
            f"{sum(1 for d in grupo if d.get('detalle_sunat'))} | "
            f"{sum(1 for d in grupo if (d.get('pdf_sunat') or {}).get('ruta'))} | "
            f"{sum(1 for d in grupo if obtener_glosa(d))} | "
            f"{', '.join(f'{n} {e.lower()}' for e, n in sorted(estados.items()))} | "
            f"{'; '.join(rutas)} |"
        )

    lineas += ["", f"## Comprobantes sin glosa ({len(sin_glosa)})", ""]
    if not sin_glosa:
        lineas.append("Ninguno.")
    else:
        lineas += [
            "| Libro | Comprobante | Tipo | Contraparte | Estado | Consultado "
            "| Última línea del log |",
            "|---|---|---|---|---|---|---|",
        ]
        for libro_txt, d in sin_glosa:
            serie_numero = str(d.get("serie_numero", ""))
            evidencia = log.get(serie_numero, "sin rastro en el log")
            evidencia = evidencia.split(" INFO ", 1)[-1].replace("|", "/")
            lineas.append(
                f"| {libro_txt} | {serie_numero} | {d.get('tipo_cp')} | "
                f"{str(d.get('razon_social') or '')[:40]} | "
                f"{ETIQUETA_ESTADO_GLOSA[estado_glosa(d)]} | "
                f"{'sí' if d.get('glosa_consultada') else 'no'} | {evidencia} |"
            )

    salida = Path(args.salida) / f"Informe_Tipos_{args.ruc}_{args.periodo}.md"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    print(f"\nGuardado en {salida}")


if __name__ == "__main__":
    main()
