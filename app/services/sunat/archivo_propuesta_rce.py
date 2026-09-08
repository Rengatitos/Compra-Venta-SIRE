"""Lectura del ZIP/CSV oficial generado por el ticket de propuesta RCE."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Any

from app.domain.comprobante import Comprobante
from app.services.sunat import rce
from app.services.sunat.auth import ErrorSunat

MAX_ARCHIVO_BYTES = 25 * 1024 * 1024


def _texto(fila: dict[str, str], columna: str) -> str:
    return (fila.get(columna) or "").strip()


def _registro_sire(fila: dict[str, str]) -> dict[str, Any]:
    """Traduce una fila del CSV al contrato que ya procesa `rce.a_comprobante`."""
    registro = {
        "perTributario": _texto(fila, "Periodo"),
        "codCar": _texto(fila, "CAR SUNAT"),
        "fecEmision": _texto(fila, "Fecha de emisión"),
        "fecVencPag": _texto(fila, "Fecha Vcto/Pago") or None,
        "codTipoCDP": _texto(fila, "Tipo CP/Doc."),
        "numSerieCDP": _texto(fila, "Serie del CDP"),
        "numCDP": _texto(fila, "Nro CP o Doc. Nro Inicial (Rango)"),
        "codTipoDocIdentidadProveedor": _texto(fila, "Tipo Doc Identidad"),
        "numDocIdentidadProveedor": _texto(fila, "Nro Doc Identidad"),
        "desRazonSocialProveedor": _texto(fila, "Apellidos Nombres/ Razón  Social"),
        "codMoneda": _texto(fila, "Moneda") or "PEN",
        "tipoCambio": {"mtoTipoCambio": _texto(fila, "Tipo de Cambio") or None},
        "montos": {
            "mtoBIGravadaDG": _texto(fila, "BI Gravado DG"),
            "mtoIgvIpmDG": _texto(fila, "IGV / IPM DG"),
            "mtoBIGravadaDGNG": _texto(fila, "BI Gravado DGNG"),
            "mtoIgvIpmDGNG": _texto(fila, "IGV / IPM DGNG"),
            "mtoBIGravadaDNG": _texto(fila, "BI Gravado DNG"),
            "mtoIgvIpmDNG": _texto(fila, "IGV / IPM DNG"),
            "mtoValorAdqNG": _texto(fila, "Valor Adq. NG"),
            "mtoISC": _texto(fila, "ISC"),
            "mtoIcbp": _texto(fila, "ICBPER"),
            "mtoOtrosTrib": _texto(fila, "Otros Trib/ Cargos"),
            "mtoTotalCp": _texto(fila, "Total CP"),
        },
    }
    # Trazabilidad completa: no se descartan las columnas libres ni de control.
    registro["archivo_ticket"] = fila
    return registro


def _decodificar(contenido: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return contenido.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ErrorSunat("El CSV de propuesta no usa UTF-8 ni Windows-1252")


def leer_zip(contenido: bytes, ruc: str, periodo: str) -> list[Comprobante]:
    if not contenido or len(contenido) > MAX_ARCHIVO_BYTES:
        raise ErrorSunat("El ZIP de propuesta está vacío o excede 25 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            entradas = [
                e
                for e in archivo.infolist()
                if not e.is_dir() and PurePosixPath(e.filename).suffix.lower() == ".csv"
            ]
            if len(entradas) != 1:
                raise ErrorSunat("El ZIP debe contener exactamente un archivo CSV")
            entrada = entradas[0]
            if entrada.file_size > MAX_ARCHIVO_BYTES:
                raise ErrorSunat("El CSV de propuesta excede 25 MB")
            texto = _decodificar(archivo.read(entrada))
    except zipfile.BadZipFile as exc:
        raise ErrorSunat("El archivo recibido no es un ZIP válido") from exc

    # El archivo descargado por el portal SIRE usa `;`. Se acepta también `,`
    # porque SUNAT ha entregado ambas variantes y los importes usan punto
    # decimal, de modo que la detección por la cabecera es inequívoca.
    primera_linea = texto.splitlines()[0] if texto.splitlines() else ""
    delimitador = ";" if primera_linea.count(";") > primera_linea.count(",") else ","
    lector = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    requeridas = {
        "RUC", "Periodo", "Tipo CP/Doc.", "Serie del CDP",
        "Nro CP o Doc. Nro Inicial (Rango)", "Moneda", "Tipo de Cambio", "Total CP",
    }
    if lector.fieldnames is None or not requeridas.issubset(lector.fieldnames):
        faltantes = sorted(requeridas - set(lector.fieldnames or []))
        raise ErrorSunat(f"CSV de propuesta incompatible; faltan columnas: {faltantes}")

    comprobantes: list[Comprobante] = []
    for numero_fila, fila in enumerate(lector, start=2):
        # El CSV real termina con una fila de totales: no tiene RUC ni
        # identidad de comprobante y repite sumas como BI/IGV. No es un CP.
        es_fila_totales = not _texto(fila, "RUC") and not any(
            _texto(fila, columna)
            for columna in (
                "Tipo CP/Doc.",
                "Serie del CDP",
                "Nro CP o Doc. Nro Inicial (Rango)",
            )
        )
        if es_fila_totales:
            continue
        if _texto(fila, "RUC") != ruc:
            raise ErrorSunat(f"El RUC del CSV no coincide en la fila {numero_fila}")
        if _texto(fila, "Periodo") != periodo:
            raise ErrorSunat(f"El periodo del CSV no coincide en la fila {numero_fila}")
        comprobante = rce.a_comprobante(_registro_sire(fila))
        comprobante.extra["origen_archivo"] = "ticket_rce_csv"
        comprobante.extra["fila_archivo"] = numero_fila
        comprobante.extra["raw_archivo"] = json.dumps(fila, ensure_ascii=False)
        if not comprobante.es_valido:
            raise ErrorSunat(f"Comprobante sin identidad válida en la fila {numero_fila}")
        comprobantes.append(comprobante)
    if not comprobantes:
        raise ErrorSunat("El CSV de propuesta no contiene comprobantes")
    return comprobantes
