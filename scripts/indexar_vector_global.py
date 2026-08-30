"""Indexa la normativa contable y tributaria en la colección `vector_global`.

`vector_global` es la base de conocimiento compartida por todas las empresas que
[cargar_vector](../app/services/analisis_ia.py) sube a memoria al arrancar el
servidor. Ningún endpoint la puebla: hasta ahora se asumía una carga manual. Este
script es esa carga.

Lee los PDFs de una carpeta, los parte en fragmentos, pide el embedding de cada
fragmento a Gemini y los inserta. No toca nada del backend: escribe documentos con
la misma forma que espera `_PROYECCION` en `app/repositories/vectores.py`
(`texto`, `metadata`, `embedding`), así que basta reiniciar la API para que el
análisis los use.

El modelo y la llamada son deliberadamente idénticos a los de `buscar_contexto`
—`models/gemini-embedding-001` sin `config`—: si aquí se pasara un `task_type` o
un `output_dimensionality` distinto, los vectores dejarían de ser comparables con
el de la consulta y la similitud de coseno devolvería basura silenciosamente.

    uv run python scripts/indexar_vector_global.py --dry-run   # sólo cuenta chunks
    uv run python scripts/indexar_vector_global.py             # indexa lo que falte
    uv run python scripts/indexar_vector_global.py --rehacer   # reindexa todo

Un embedding ya calculado se importa sin gastar cuota de Gemini, siempre que sus
vectores vengan del mismo modelo (se valida la dimensión contra una consulta real):

    uv run python scripts/indexar_vector_global.py \\
        --importar-json source/normativa/vector_db.json

y un PDF ya cubierto en parte por ese JSON se acota al tramo que falta:

    uv run python scripts/indexar_vector_global.py \\
        --paginas VERSION_MODIFICADA_PCG_EMPRESARIAL.pdf=166-239
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import pymupdf
from dotenv import load_dotenv
from google.genai.errors import APIError
from motor.motor_asyncio import AsyncIOMotorClient

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
load_dotenv(RAIZ / ".env")

from app.repositories._mongo import NOMBRE_COL_VECTOR_GLOBAL  # noqa: E402
from app.services.analisis_ia import _get_client  # noqa: E402

MODELO_EMBEDDING = "models/gemini-embedding-001"

CARPETA_POR_DEFECTO = RAIZ / "source" / "normativa"

# Un fragmento demasiado largo diluye el parecido con el texto del comprobante,
# que son dos o tres líneas; uno demasiado corto pierde el artículo o la cuenta a
# la que pertenece. ~1200 caracteres deja un párrafo normativo completo.
MAX_CHARS = 1200
SOLAPE = 150
# Páginas de índice, carátulas y separadores: nunca aportan contexto y ensucian
# el top-k, que en `buscar_contexto` es fijo en 20.
MIN_CHARS = 220


def _normalizar(texto: str) -> str:
    # PyMuPDF corta cada línea del PDF con \n, así que un párrafo llega troceado.
    # Sin esto los fragmentos quedan llenos de saltos y las palabras partidas por
    # guion al final de renglón se indexan como dos palabras distintas.
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"-\n(?=[a-záéíóúñ])", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{2,}", "\n\n", texto)
    return texto.strip()


def _utiles(texto: str) -> int:
    return len(re.sub(r"[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ]", "", texto))


def _partir(texto: str, max_chars: int, solape: int) -> list[str]:
    """Parte por párrafos y, si un párrafo excede el máximo, por oraciones."""
    piezas: list[str] = []
    for parrafo in [p.strip() for p in texto.split("\n\n") if p.strip()]:
        if len(parrafo) <= max_chars:
            piezas.append(parrafo)
            continue
        actual = ""
        for oracion in re.split(r"(?<=[.;:])\s+", parrafo):
            if len(actual) + len(oracion) + 1 <= max_chars:
                actual = f"{actual} {oracion}".strip()
                continue
            if actual:
                piezas.append(actual)
            # Una sola oración más larga que el máximo (tablas del PCGE, listas
            # de partidas arancelarias del Apéndice I): se corta a lo bruto.
            while len(oracion) > max_chars:
                piezas.append(oracion[:max_chars])
                oracion = oracion[max_chars - solape :]
            actual = oracion
        if actual:
            piezas.append(actual)

    fragmentos: list[str] = []
    buffer = ""
    for pieza in piezas:
        if not buffer:
            buffer = pieza
        elif len(buffer) + len(pieza) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{pieza}"
        else:
            fragmentos.append(buffer)
            # El solape evita que una definición que cae justo en el corte quede
            # sin la frase que la introduce.
            cola = buffer[-solape:] if solape else ""
            buffer = f"{cola}\n\n{pieza}".strip() if cola else pieza
    if buffer:
        fragmentos.append(buffer)
    return fragmentos


def trocear_pdf(
    ruta: Path,
    max_chars: int,
    solape: int,
    rango: tuple[int, int] | None = None,
) -> list[dict[str, Any]]:
    documento = pymupdf.open(ruta)
    chunks: list[dict[str, Any]] = []
    try:
        for numero, pagina in enumerate(documento, start=1):
            if rango and not (rango[0] <= numero <= rango[1]):
                continue
            texto = _normalizar(pagina.get_text("text"))
            if _utiles(texto) < MIN_CHARS:
                continue
            orden = 0
            for fragmento in _partir(texto, max_chars, solape):
                if _utiles(fragmento) < MIN_CHARS:
                    continue
                chunks.append(
                    {
                        "texto": fragmento,
                        "metadata": {
                            "documento": ruta.name,
                            "pagina": numero,
                            # Clave de reanudación. Va anclada a la página y no a
                            # un contador global para que siga identificando al
                            # mismo fragmento aunque se indexe otro rango.
                            "chunk": f"{numero}-{orden}",
                        },
                    }
                )
                orden += 1
    finally:
        documento.close()
    return chunks


def _retry_delay(exc: APIError) -> float | None:
    detalles = exc.details if isinstance(exc.details, dict) else {}
    for item in detalles.get("error", {}).get("details", []):
        valor = item.get("retryDelay")
        if valor:
            match = re.match(r"([\d.]+)", str(valor))
            if match:
                return float(match.group(1))
    return None


class Embebedor:
    """Llama a Gemini por lotes, respetando el límite de peticiones por minuto."""

    def __init__(self, rpm: int, reintentos: int = 5) -> None:
        self.intervalo = 60.0 / max(rpm, 1)
        self.reintentos = reintentos
        self._ultima = 0.0

    def _esperar_turno(self) -> None:
        espera = self._ultima + self.intervalo - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.monotonic()

    def __call__(self, textos: list[str]) -> list[list[float]]:
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            try:
                respuesta = _get_client().models.embed_content(
                    model=MODELO_EMBEDDING,
                    contents=textos,
                )
                return [list(e.values) for e in respuesta.embeddings]
            except APIError as exc:
                if intento == self.reintentos:
                    raise
                espera = _retry_delay(exc) or min(2**intento, 60)
                print(
                    f"    aviso: {exc.code if hasattr(exc, 'code') else 'APIError'}; "
                    f"reintento {intento}/{self.reintentos - 1} en {espera:.0f}s",
                    flush=True,
                )
                time.sleep(espera)
        return []


def _dimension_de_consulta() -> int:
    """Dimensión que produce `buscar_contexto` al embeber el texto del comprobante.

    Es la única referencia válida: si un embedding importado no la respeta, el
    producto punto de `buscar_contexto` revienta, la excepción se traga en su
    `except` y el análisis se queda sin contexto normativo sin avisar.
    """
    respuesta = _get_client().models.embed_content(
        model=MODELO_EMBEDDING, contents="verificacion de dimension"
    )
    return len(respuesta.embeddings[0].values)


async def importar_json(coleccion, ruta: Path, rehacer: bool) -> int:
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(datos, list) or not datos:
        print(f"{ruta.name}: no es una lista de chunks")
        return 0

    esperada = _dimension_de_consulta()
    dimensiones = {len(x.get("embedding") or []) for x in datos}
    if dimensiones != {esperada}:
        print(
            f"{ruta.name}: dimensiones {sorted(dimensiones)} incompatibles con las "
            f"{esperada} que genera la consulta. No se importa."
        )
        return 0

    documentos = sorted({x.get("metadata", {}).get("documento", "?") for x in datos})
    if rehacer:
        borrados = await coleccion.delete_many({"metadata.documento": {"$in": documentos}})
        print(f"{ruta.name}: {borrados.deleted_count} chunks previos eliminados")
    else:
        ya = await coleccion.count_documents({"metadata.documento": {"$in": documentos}})
        if ya:
            print(f"{ruta.name}: ya hay {ya} chunks de {documentos}; se omite (usa --rehacer)")
            return 0

    await coleccion.insert_many(
        [
            {"texto": x["texto"], "metadata": x.get("metadata", {}), "embedding": x["embedding"]}
            for x in datos
            if (x.get("texto") or "").strip()
        ]
    )
    print(f"{ruta.name}: {len(datos)} chunks importados (dim {esperada}) de {documentos}")
    return len(datos)


def _parsear_rangos(valores: list[str]) -> dict[str, tuple[int, int]]:
    rangos: dict[str, tuple[int, int]] = {}
    for valor in valores:
        nombre, _, tramo = valor.partition("=")
        desde, _, hasta = tramo.partition("-")
        if not nombre or not desde.isdigit():
            raise SystemExit(f"--paginas mal formado: {valor!r} (usa ARCHIVO.pdf=166-239)")
        rangos[nombre] = (int(desde), int(hasta) if hasta.isdigit() else 10**9)
    return rangos


async def indexar(args: argparse.Namespace) -> int:
    carpeta = Path(args.carpeta)
    rangos = _parsear_rangos(args.paginas)
    omitir = set(args.omitir)
    pdfs = [p for p in sorted(carpeta.glob("*.pdf")) if p.name not in omitir]
    if not pdfs and not args.importar_json:
        print(f"No hay PDFs en {carpeta}")
        return 1

    troceados = {
        p: trocear_pdf(p, args.max_chars, args.solape, rangos.get(p.name)) for p in pdfs
    }
    total = sum(len(c) for c in troceados.values())
    print(f"Carpeta: {carpeta}")
    for p, chunks in troceados.items():
        largos = [len(c["texto"]) for c in chunks] or [0]
        tramo = f"  págs {rangos[p.name][0]}-{rangos[p.name][1]}" if p.name in rangos else ""
        print(
            f"  {p.name:48s} {len(chunks):4d} chunks "
            f"(prom {sum(largos) // len(largos)} car.){tramo}"
        )
    for nombre in sorted(omitir):
        print(f"  {nombre:48s}    - omitido")
    print(f"  {'TOTAL A EMBEBER':48s} {total:4d} chunks")

    if args.dry_run:
        print("\n--dry-run: no se llamó a Gemini ni se escribió en Mongo.")
        return 0

    uri = os.environ.get("MONGO_URI")
    base = os.environ.get("MONGO_FACTURASDB_NAME")
    if not uri or not base:
        print("Falta MONGO_URI o MONGO_FACTURASDB_NAME en el entorno")
        return 1

    cliente = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=15000)
    coleccion = cliente[base][NOMBRE_COL_VECTOR_GLOBAL]
    # El mismo índice que crea `vectores.crear_indices` al arrancar la API.
    await coleccion.create_index([("metadata.documento", 1)])

    insertados = 0
    if args.importar_json:
        insertados += await importar_json(coleccion, Path(args.importar_json), args.rehacer)

    embebedor = Embebedor(rpm=args.rpm)

    for ruta, chunks in troceados.items():
        if not chunks:
            continue
        if args.rehacer:
            borrados = await coleccion.delete_many({"metadata.documento": ruta.name})
            if borrados.deleted_count:
                print(f"\n{ruta.name}: {borrados.deleted_count} chunks previos eliminados")
            hechos: set[int] = set()
        else:
            hechos = set(
                await coleccion.distinct("metadata.chunk", {"metadata.documento": ruta.name})
            )

        pendientes = [c for c in chunks if c["metadata"]["chunk"] not in hechos]
        print(f"\n{ruta.name}: {len(pendientes)} por indexar de {len(chunks)}")
        if not pendientes:
            continue

        for inicio in range(0, len(pendientes), args.lote):
            lote = pendientes[inicio : inicio + args.lote]
            vectores = embebedor([c["texto"] for c in lote])
            if len(vectores) != len(lote):
                print(
                    f"    error: Gemini devolvió {len(vectores)} vectores "
                    f"para {len(lote)} textos"
                )
                return 1
            await coleccion.insert_many(
                [
                    {"texto": c["texto"], "metadata": c["metadata"], "embedding": v}
                    for c, v in zip(lote, vectores, strict=True)
                ]
            )
            insertados += len(lote)
            print(
                f"    {min(inicio + args.lote, len(pendientes)):4d}/{len(pendientes)} "
                f"(dim {len(vectores[0])})",
                flush=True,
            )

    final = await coleccion.count_documents({})
    print(f"\nInsertados {insertados} chunks. `vector_global` tiene ahora {final}.")
    print("Reinicia la API para que `cargar_vector` los suba a memoria.")
    cliente.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--carpeta", default=str(CARPETA_POR_DEFECTO))
    parser.add_argument("--dry-run", action="store_true", help="sólo cuenta fragmentos")
    parser.add_argument("--rehacer", action="store_true", help="reindexa lo ya cargado")
    parser.add_argument(
        "--importar-json", help="embedding ya calculado, en el formato de vector_global"
    )
    parser.add_argument(
        "--paginas",
        action="append",
        default=[],
        metavar="ARCHIVO.pdf=DESDE-HASTA",
        help="acota un PDF a un tramo de páginas (repetible)",
    )
    parser.add_argument(
        "--omitir", action="append", default=[], metavar="ARCHIVO.pdf", help="salta un PDF"
    )
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    parser.add_argument("--solape", type=int, default=SOLAPE)
    parser.add_argument("--lote", type=int, default=16, help="textos por petición")
    parser.add_argument("--rpm", type=int, default=60, help="peticiones por minuto")
    return asyncio.run(indexar(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
