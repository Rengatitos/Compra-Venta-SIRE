"""Recompone el motivo de las clasificaciones ya guardadas con el formato actual.

El motivo dice qué es cada cuenta según el plan de cuentas (su camino: 60
COMPRAS › 602 MATERIAS PRIMAS › …) y por qué la eligió la IA. Las
clasificaciones anteriores a ese formato solo tenían el texto de la IA, o una
frase de «reutilizada» sin el porqué.

- Clasificadas por la IA: el porqué sale de su propio texto original.
- Reutilizadas: el porqué sale de la clasificación frecuente; si esa no lo
  tiene, se busca en algún comprobante con la misma glosa que lo conserve.

Idempotente: el texto original de la IA queda en `razon_ia` y se parte de él.

    uv run python scripts/recomponer_motivos.py            # muestra qué haría
    uv run python scripts/recomponer_motivos.py --aplicar  # escribe
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
from app.repositories._mongo import (  # noqa: E402
    NOMBRE_COL_CLASIFICACIONES_FRECUENTES,
    NOMBRE_COL_COMPROBANTES,
)
from app.services.clasificacion_service import completar_motivo, resumir_motivo  # noqa: E402
from app.services.glosa import obtener_glosa  # noqa: E402

# Así empieza un motivo ya compuesto; lo demás es texto original de la IA.
_COMPUESTO = (
    "Cuenta base ", "Sin cuenta base", "Reutilizada de una clasificación frecuente",
    "Corregida por un usuario",
)


def _texto_ia(clasificacion: dict) -> str:
    if clasificacion.get("razon_ia"):
        return clasificacion["razon_ia"]
    razon = clasificacion.get("razon") or ""
    return "" if razon.startswith(_COMPUESTO) or "También reutilizado" in razon else razon


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="escribe en Mongo")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URI"])[os.environ["MONGO_FACTURASDB_NAME"]]
    comprobantes = db[NOMBRE_COL_COMPROBANTES]
    frecuentes = db[NOMBRE_COL_CLASIFICACIONES_FRECUENTES]

    documentos = await comprobantes.find(
        {"clasificacion_contable": {"$exists": True}}
    ).to_list(length=None)

    # Textos originales de la IA que se conservan, por (empresa, libro, glosa).
    originales: dict[tuple, str] = {}
    for doc in documentos:
        texto = _texto_ia(doc["clasificacion_contable"])
        glosa = obtener_glosa(doc)
        if texto and doc["clasificacion_contable"].get("origen") != "memoria" and glosa:
            originales.setdefault((doc["empresa_id"], doc["libro"], clave(glosa)), texto)

    entradas = {}
    async for entrada in frecuentes.find({}):
        if not entrada.get("razon"):
            recuperado = originales.get((entrada["empresa_id"], entrada["libro"], entrada["clave"]))
            if recuperado:
                entrada["razon"] = recuperado
                if args.aplicar:
                    await frecuentes.update_one(
                        {"_id": entrada["_id"]}, {"$set": {"razon": recuperado}}
                    )
        entradas[str(entrada["_id"])] = entrada

    cuenta = {"ia": 0, "memoria": 0, "sin_porque": 0}
    ejemplo = None
    for doc in documentos:
        c = dict(doc["clasificacion_contable"])
        if c.get("origen") == "memoria":
            entrada = entradas.get(c.get("memoria_id") or "") or {}
            texto = entrada.get("razon") or _texto_ia(c)
            glosa_origen = entrada.get("glosa") or obtener_glosa(doc)
            reutilizado = (
                f"También reutilizado: misma glosa que «{glosa_origen}», "
                "sin volver a consultar a la IA."
            )
            confirmada = entrada.get("origen") == "usuario"
            cuenta["memoria"] += 1
        else:
            texto, reutilizado, confirmada = _texto_ia(c), None, False
            cuenta["ia"] += 1
        c["razon_ia"] = texto
        por_que = resumir_motivo(texto)
        cuenta["sin_porque"] += not por_que
        c = await completar_motivo(
            db, doc["empresa_id"], c, por_que, confirmada=confirmada, reutilizado=reutilizado
        )
        ejemplo = ejemplo or (doc["serie_numero"], c["razon"])
        if args.aplicar:
            await comprobantes.update_one(
                {"_id": doc["_id"]}, {"$set": {"clasificacion_contable": c}}
            )

    print(f"{cuenta['ia']} clasificados por la IA y {cuenta['memoria']} reutilizados recompuestos; "
          f"{cuenta['sin_porque']} sin razonamiento original disponible.")
    if ejemplo:
        print(f"\nEjemplo {ejemplo[0]}:\n{ejemplo[1]}")
    if not args.aplicar:
        print("\nNada escrito. Repite con --aplicar para guardar.")


asyncio.run(main())
