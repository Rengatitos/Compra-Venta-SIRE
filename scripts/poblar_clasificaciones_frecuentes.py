"""Crea las clasificaciones frecuentes a partir de lo ya clasificado.

Las clasificaciones hechas antes de que existiera la memoria de frecuentes no
dejaron entrada: este script las registra (una por glosa distinta, por
empresa y libro) y enlaza cada comprobante con la suya, para que corregirla
desde el panel también lo actualice. Las confiables pasan a reutilizarse.

Si una glosa tiene varias clasificaciones, gana la más confiable: primero las
que no piden revisión, luego la de mayor confianza.

    uv run python scripts/poblar_clasificaciones_frecuentes.py            # muestra qué haría
    uv run python scripts/poblar_clasificaciones_frecuentes.py --aplicar  # escribe
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv()

from app.domain.glosa_similar import clave  # noqa: E402
from app.repositories import clasificaciones_frecuentes as repo_frecuentes  # noqa: E402
from app.repositories._mongo import NOMBRE_COL_COMPROBANTES  # noqa: E402
from app.services.glosa import obtener_glosa  # noqa: E402


def _mejor(actual: dict | None, nuevo: dict) -> bool:
    if actual is None:
        return True
    a, n = actual["clasificacion_contable"], nuevo["clasificacion_contable"]
    return (not n.get("requiere_revision", True), n.get("confianza", 0)) > (
        not a.get("requiere_revision", True), a.get("confianza", 0)
    )


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="escribe en Mongo")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URI"])[os.environ["MONGO_FACTURASDB_NAME"]]
    comprobantes = db[NOMBRE_COL_COMPROBANTES]
    if args.aplicar:
        await repo_frecuentes.crear_indices(db)

    grupos: dict[tuple[str, str, str], dict] = {}
    miembros: dict[tuple[str, str, str], list] = {}
    async for doc in comprobantes.find({
        "clasificacion_contable": {"$exists": True},
        "clasificacion_contable.origen": {"$ne": "memoria"},
    }):
        glosa = obtener_glosa(doc)
        if not glosa or not clave(glosa):
            continue
        llave = (doc["empresa_id"], doc["libro"], clave(glosa))
        miembros.setdefault(llave, []).append(doc["_id"])
        if _mejor(grupos.get(llave), doc):
            grupos[llave] = {**doc, "_glosa": glosa}

    confiables = 0
    for (empresa_id, libro, clave_), doc in grupos.items():
        clasificacion = doc["clasificacion_contable"]
        confiable = not clasificacion.get("requiere_revision", True)
        confiables += confiable
        cuenta = (clasificacion.get("cuenta_base") or {}).get("codigo") or "sin cuenta"
        print(f"{libro:7} {cuenta:10} {'confiable' if confiable else 'por revisar':11} "
              f"{len(miembros[(empresa_id, libro, clave_)])}x  {doc['_glosa'][:60]}")
        if args.aplicar:
            entrada_id = await repo_frecuentes.registrar_de_ia(
                db, empresa_id, libro, clave_, doc["_glosa"], clasificacion
            )
            await comprobantes.update_many(
                {"_id": {"$in": miembros[(empresa_id, libro, clave_)]}},
                {"$set": {"clasificacion_contable.memoria_id": str(entrada_id)}},
            )

    print(f"\n{len(grupos)} glosas distintas, {confiables} confiables (se reutilizarán).")
    if not args.aplicar:
        print("Nada escrito. Repite con --aplicar para guardar.")


asyncio.run(main())
