"""Recalcula los importes de los comprobantes ya guardados.

Cada comprobante conserva la respuesta cruda del SIRE en `extra.raw_sire`, así
que volver a mapearla no cuesta ni una llamada a SUNAT. Sirve cuando el mapeo
cambia y los documentos existentes quedaron con importes viejos —por ejemplo
los que se guardaron mientras la base imponible y el IGV se leían con nombres
de campo que el SIRE no envía nunca y llegaban siempre en cero.

    uv run python scripts/recalcular_importes.py            # muestra qué haría
    uv run python scripts/recalcular_importes.py --aplicar  # escribe
    uv run python scripts/recalcular_importes.py --aplicar --ruc 20603391692
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()

from app.domain.comprobante import Libro  # noqa: E402
from app.repositories._mongo import (  # noqa: E402
    NOMBRE_COL_COMPROBANTES,
    monto_a_bson,
    monto_a_float,
)
from app.repositories.comprobantes import _CAMPOS_MONTO  # noqa: E402
from app.services.sunat.propuesta import a_comprobante  # noqa: E402


def _recalcular(documento: dict[str, Any]) -> dict[str, Any] | None:
    """Devuelve sólo los campos cuyo importe cambia, o None si no cambia nada."""
    crudo = (documento.get("extra") or {}).get("raw_sire")
    if not crudo:
        return None

    try:
        registro = json.loads(crudo)
    except (TypeError, ValueError):
        return None

    libro = Libro(documento.get("libro", Libro.COMPRAS.value))
    recalculado = a_comprobante(registro, libro)

    cambios: dict[str, Any] = {}
    for campo in _CAMPOS_MONTO:
        nuevo = getattr(recalculado, campo)
        if monto_a_float(documento.get(campo)) != float(nuevo):
            cambios[campo] = monto_a_bson(nuevo)
    return cambios or None


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--aplicar",
        action="store_true",
        help="escribe los cambios (por defecto solo los lista)",
    )
    ap.add_argument("--ruc", help="limita a una empresa")
    ap.add_argument("--periodo", help="limita a un periodo, p. ej. 202601")
    args = ap.parse_args()

    cli = AsyncIOMotorClient(os.environ["MONGO_URI"])
    db = cli[os.environ["MONGO_FACTURASDB_NAME"]]

    filtro: dict[str, Any] = {}
    if args.ruc:
        empresa = await db["empresas"].find_one({"ruc": args.ruc})
        if not empresa:
            print(f"no existe la empresa {args.ruc}")
            cli.close()
            return
        filtro["empresa_id"] = str(empresa["_id"])
    if args.periodo:
        filtro["periodo"] = args.periodo

    documentos = await db[NOMBRE_COL_COMPROBANTES].find(filtro).to_list(None)
    print(f"comprobantes revisados: {len(documentos)}")

    sin_crudo = 0
    pendientes: list[tuple[Any, str, dict[str, Any]]] = []
    for documento in documentos:
        if not (documento.get("extra") or {}).get("raw_sire"):
            sin_crudo += 1
            continue
        cambios = _recalcular(documento)
        if cambios:
            pendientes.append((documento["_id"], documento.get("serie_numero", "?"), cambios))

    if sin_crudo:
        print(f"  sin raw_sire (no se pueden recalcular): {sin_crudo}")
    print(f"  con importes que cambian: {len(pendientes)}\n")

    for _, serie_numero, cambios in pendientes[:40]:
        detalle = ", ".join(f"{c}={monto_a_float(v)}" for c, v in sorted(cambios.items()))
        print(f"  {serie_numero:<18} {detalle}")
    if len(pendientes) > 40:
        print(f"  ... y {len(pendientes) - 40} más")

    if not args.aplicar:
        print("\nsimulacion: vuelve a lanzarlo con --aplicar para escribir")
        cli.close()
        return

    for documento_id, _, cambios in pendientes:
        await db[NOMBRE_COL_COMPROBANTES].update_one({"_id": documento_id}, {"$set": cambios})

    print(f"\nactualizados {len(pendientes)} comprobantes")
    cli.close()


asyncio.run(main())
