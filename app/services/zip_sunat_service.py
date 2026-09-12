"""ZIP nuevo de ambos registros, con PDFs obtenidos en la ejecución actual."""

import asyncio
import csv
import io
import re
import zipfile
from datetime import UTC, datetime, timedelta

from app.domain.comprobante import Libro
from app.repositories import comprobantes
from app.services import almacen_pdf, scraping_sunat

CARPETAS = {Libro.COMPRAS: "comprobantes compra", Libro.VENTAS: "comprobantes venta"}


def ruta_archivo(ruc: str, job_id: str):
    if not re.fullmatch(r"[0-9]{11}", ruc) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Identificador de archivo inválido")
    return almacen_pdf.raiz() / ruc / "zip_sunat" / f"{job_id}.zip"


def nombre_archivo(usuario: str) -> str:
    codigo = re.sub(r"[^A-Za-z0-9_-]", "", usuario)
    if not codigo:
        raise ValueError("Usuario SOL inválido para el nombre del ZIP")
    fecha = (datetime.now(UTC) - timedelta(hours=5)).strftime("%d%m%Y")
    return f"{fecha}_{codigo}.zip"


def _lotes(filas):
    # El callback del scraper identifica por serie-número. Separar las
    # colisiones evita asignar el PDF de otro proveedor o tipo de comprobante.
    lote = {}
    for fila in filas:
        clave = fila["serie_numero"]
        if clave in lote:
            yield lote
            lote = {}
        lote[clave] = fila
    if lote:
        yield lote


async def preparar(db, empresa, periodo, job_id, reportar):
    registros = {}
    for libro in CARPETAS:
        filas = []
        while True:
            pagina = await comprobantes.listar(
                db, str(empresa["_id"]), periodo, libro=libro, skip=len(filas), limit=500
            )
            filas.extend(pagina)
            if len(pagina) < 500:
                break
        registros[libro] = filas
    total = sum(len(filas) for filas in registros.values())
    if not total:
        raise ValueError("No hay comprobantes en compras ni ventas para este periodo")
    nombre = nombre_archivo(empresa["usuario"])
    ruta = ruta_archivo(empresa["ruc"], job_id)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    hechos = descargados = 0
    faltantes = []
    loop = asyncio.get_running_loop()
    try:
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as archivo:
            for carpeta in CARPETAS.values():
                archivo.writestr(carpeta + "/", b"")
            for libro, filas in registros.items():
                for lote in _lotes(filas):
                    guardados = set()

                    def guardar(clave, contenido, lote=lote, guardados=guardados, libro=libro):
                        if clave not in lote or clave in guardados:
                            return
                        if not contenido.startswith(b"%PDF-"):
                            return
                        fila = lote[clave]
                        emisor = scraping_sunat._ruc_emisor(fila, libro, empresa["ruc"])
                        partes = [
                            emisor,
                            fila.get("tipo_cp"),
                            fila.get("serie"),
                            fila.get("numero"),
                            str(fila["_id"]),
                        ]
                        nombre_pdf = (
                            "_".join(almacen_pdf._segmento(p, campo="PDF") for p in partes) + ".pdf"
                        )
                        archivo.writestr(f"{CARPETAS[libro]}/{nombre_pdf}", contenido)
                        guardados.add(clave)

                    def progreso(actual, clave, hechos=hechos, libro=libro):
                        asyncio.run_coroutine_threadsafe(
                            reportar(hechos + actual, total, f"Descargando {libro.value}: {clave}"),
                            loop,
                        ).result()

                    await scraping_sunat.obtener_detalles(
                        empresa,
                        list(lote.values()),
                        libro=libro,
                        headed=False,
                        descargar_pdf=True,
                        al_descargar=guardar,
                        progreso=progreso,
                    )
                    descargados += len(guardados)
                    hechos += len(lote)
                    for clave, fila in lote.items():
                        if clave not in guardados:
                            faltantes.append(
                                [
                                    libro.value,
                                    fila.get("documento_contraparte", ""),
                                    fila.get("tipo_cp", ""),
                                    clave,
                                ]
                            )
            if faltantes:
                salida = io.StringIO()
                escritor = csv.writer(salida, delimiter=";")
                escritor.writerow(["registro", "contraparte", "tipo", "comprobante"])
                escritor.writerows(faltantes)
                archivo.writestr("faltantes.csv", salida.getvalue().encode("utf-8-sig"))
        if not descargados:
            raise ValueError("SUNAT no entregó ningún PDF. Revisa el proceso y vuelve a intentar")
    except BaseException:
        ruta.unlink(missing_ok=True)
        raise
    await reportar(total, total, f"{descargados} PDFs descargados; {len(faltantes)} sin PDF")
    return {
        "nombre": nombre,
        "descargados": descargados,
        "sin_pdf": len(faltantes),
        "procesados": total,
        "zip_completo": True,
    }
