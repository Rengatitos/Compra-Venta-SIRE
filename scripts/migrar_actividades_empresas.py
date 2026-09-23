"""Copia las actividades económicas de los JSON de `company_heads` a Mongo.

La API del clasificador guardaba el contexto de cada empresa en un JSON por
RUC (`data/company_heads/{ruc}.json`). Integrada en esta API, ese contexto vive
en el documento de la empresa, en `actividades_economicas`, y se edita con
`PUT /api/v1/empresas/{ruc}`. Este script hace el traspaso una vez.

Sólo toca empresas ya registradas; los RUC sin empresa se listan y se saltan.

    uv run python scripts/migrar_actividades_empresas.py            # muestra qué haría
    uv run python scripts/migrar_actividades_empresas.py --aplicar  # escribe
    uv run python scripts/migrar_actividades_empresas.py --dir otra/carpeta --aplicar
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
load_dotenv()

from app.repositories._mongo import NOMBRE_COL_EMPRESAS  # noqa: E402
from app.schemas.empresa import ActividadEconomica  # noqa: E402

DIR_POR_DEFECTO = RAIZ / "codigo sin integrar" / "data" / "company_heads"


def _actividades(cabeza: dict) -> list[dict]:
    return [
        ActividadEconomica(
            tipo=a.get("tipo"),
            ciiu=str(a.get("ciiu_v4") or a.get("ciiu") or ""),
            descripcion=a.get("descripcion"),
        ).model_dump()
        for a in cabeza.get("actividades_economicas") or []
        if a.get("ciiu_v4") or a.get("ciiu")
    ]


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="escribe en Mongo")
    ap.add_argument("--dir", type=Path, default=DIR_POR_DEFECTO, help="carpeta con los JSON")
    args = ap.parse_args()

    archivos = sorted(args.dir.glob("*.json"))
    if not archivos:
        sys.exit(f"No hay JSON en {args.dir}")

    cli = AsyncIOMotorClient(os.environ["MONGO_URI"])
    col = cli[os.environ["MONGO_FACTURASDB_NAME"]][NOMBRE_COL_EMPRESAS]
    for archivo in archivos:
        cabeza = json.loads(archivo.read_text(encoding="utf-8"))
        ruc = str(cabeza.get("ruc") or "").strip()
        actividades = _actividades(cabeza)
        empresa = await col.find_one({"ruc": ruc}, {"_id": 1})
        if empresa is None:
            print(f"{ruc}: sin empresa registrada, se salta")
            continue
        ciius = ", ".join(a["ciiu"] for a in actividades)
        print(f"{ruc}: {len(actividades)} actividades ({ciius})")
        if args.aplicar:
            await col.update_one(
                {"_id": empresa["_id"]}, {"$set": {"actividades_economicas": actividades}}
            )
    if not args.aplicar:
        print("\nNada escrito. Repite con --aplicar para guardar.")


asyncio.run(main())
