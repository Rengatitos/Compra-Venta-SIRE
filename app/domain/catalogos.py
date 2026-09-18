TIPO_DOC_IDENTIDAD: dict[str, str] = {
    "0": "OTROS TIPOS DE DOCUMENTOS",
    "1": "DNI / DOCUMENTO NACIONAL DE IDENTIDAD",
    "4": "CARNET DE EXTRANJERIA",
    "6": "RUC / REGISTRO UNICO DE CONTRIBUYENTES",
    "7": "PASAPORTE",
    "A": "CEDULA DIPLOMATICA DE IDENTIDAD",
}

# Transcrito de las imágenes de source/CODIGOS DE TIPOS PARA CONTASIS.docx.
# La tabla salta de 46 a 48: el código 47 no existe.
TIPO_COMPROBANTE: dict[str, str] = {
    "00": "OTROS",
    "01": "FACTURA",
    "02": "RECIBO DE HONORARIOS",
    "03": "BOLETA DE VENTA",
    "04": "LIQUIDACION DE COMPRA",
    "05": "BOLETO TRANS. AEREO PASAJEROS",
    "06": "BOLETO TRANS. AEREO CARGA",
    "07": "NOTA DE CREDITO",
    "08": "NOTA DE DEBITO",
    "09": "GUIA DE REMISION - REMITENTE",
    "10": "RECIBO POR ARRENDAMIENTO",
    "11": "POLIZA BOLSA DE VAL, PRODU OTR",
    "12": "TICKET MAQUINA REGISTRADORA",
    "13": "DOCUMENTO ENTIDADES FINANCIERA",
    "14": "RECIBO SERV. PUBLICOS",
    "15": "BOLETO TRANSP PUBLIC URBANO",
    "16": "BOLETO DE VIAJE TRANSP PASAJER",
    "17": "DOCUM IGLESIA CATOLICA ARREND",
    "18": "DOCUMENTO EMITIDO POR AFPs",
    "19": "BOLETO EVENTOS PUBLICOS",
    "20": "COMPROBANTE DE RETENCION",
    "21": "CONOC EMBARQU TRANS CARGA MARI",
    "22": "COMPROB. OPER. NO HABITUALES",
    "23": "POLIZA ADJUD REMATE VENTA MART",
    "24": "CERTIF. PAGO REGALIA PERUPETRO",
    "25": "DOCUMENTO DE ATRIBUCION - IGV",
    "26": "RECIB. SERV AGUA FINES AGRARIO",
    "27": "SCTR - SEGUR COMPL TRAB RIESGO",
    "28": "TARIF UNIFICADA USO AEROPUERTO",
    "29": "DOCUM. EMITIDO POR COFOPRI",
    "30": "DOC EMPR ADQUI TARJ CRED DEBIT",
    # 31, 32, 34-37, 42 y 64 no están en el documento de Contasis; se toman
    # de la Tabla 3 del anexo de estructura del SIRE.
    "31": "GUIA DE REMISION - TRANSPORTISTA",
    "32": "DOC RECAUDADORAS GARANTIA RED",
    "34": "DOCUMENTO DEL OPERADOR",
    "35": "DOCUMENTO DEL PARTICIPE",
    "36": "RECIBO DISTRIBUCION GAS NATURAL",
    "37": "DOC CONCESIONARIOS REV TECNICA",
    "42": "DOC ADQUIRENTE TARJ PROPIAS",
    "43": "BOL. AVIA COMER NO REGUL PASAJ",
    "44": "BILLET DE LOTERIA, RIFA Y APUE",
    "45": "DOC EMIT CENT EDUC NO GRAVADOS",
    "46": "FORMULARIO DE DECLARACION VI",
    "48": "COMPROBANTE DE OPERACIONES - LEY N 29972",
    "49": "CONSTANCIA DE DEPOSITO - IVAP",
    "50": "DECLARACION UNICA ADUANAS - ID",
    "51": "POLIZA O DUI FRACCIONADA",
    "52": "DESPACHO SIMPLIF. - IMPOR SIMP",
    "53": "DECLARACION MENSAJERIA COURIER",
    "54": "LIQUIDACION DE COBRANZA",
    "55": "BVME TRANS FERROV PASAJEROS",
    "56": "COMPROBANTE PAGO SEAE",
    "64": "DOC SERV TRANSPORTE AEREO PASAJ",
    "87": "NOTA DE CREDITO ESPECIAL",
    "88": "NOTA DE DEBITO ESPECIAL",
    "89": "NOTA DE AJUSTE DE OPERACIONES - LEY N 29972",
    "91": "COMPROBANTE DE NO DOMICILIADO",
    "96": "EXCESO CRED FISC x RETIRO BIEN",
    "97": "NOTA CREDITO - NO DOMICILIADO",
    "98": "NOTA DEBITO - NO DOMICILIADO",
    "CH": "CHEQUE",
    "DP": "DEPOSITO",
    "LA": "LIBRO DE ACTAS",
    "LE": "LETRA DE CAMBIO",
    "LI": "LIQUIDACION",
}

TIPOS_NOTA_CREDITO = frozenset({"07", "87", "97"})
TIPOS_NOTA_DEBITO = frozenset({"08", "88", "98"})

# Qué publica SUNAT de cada tipo de comprobante, según el alcance acordado con
# el cliente el 12-sep-2026 (`Alcance_Glosa_Comprobantes_Compras_Ventas.docx`,
# a partir de la Tabla 3 del anexo de estructura del SIRE). Decide el estado de
# la glosa (`app/services/glosa.py::estado_glosa`) y qué comprobantes se saltan
# al consultar el portal SOL.
#
# Con detalle en SUNAT: el portal lista el comprobante y la glosa sale de sus
# ítems. Incluye los 4 tipos verificados (01, 03, 07, 30) y los 14 que el
# scraper trata igual pero aún no se han probado con casos reales (08, 13, 14,
# 18, 19, 23, 29, 34, 35, 36, 42, 64, 87, 88).
TIPOS_CON_DETALLE_SUNAT = frozenset({
    "01", "03", "07", "08", "13", "14", "18", "19", "23", "29",
    "30", "34", "35", "36", "42", "64", "87", "88",
})

# Sin detalle en SUNAT: el portal no publica el contenido. Se entregan con los
# datos del SIRE y sin glosa, y no se consultan en SOL.
TIPOS_SIN_DETALLE_SUNAT = frozenset({
    "00", "04", "05", "06", "11", "12", "15", "16", "17", "21", "24", "27",
    "28", "32", "37", "43", "44", "45", "48", "49", "55", "56", "89",
})

# En evaluación: falta determinar si SUNAT publica su detalle. Cualquier código
# fuera de las tres listas se trata igual.
TIPOS_EN_EVALUACION = frozenset({
    "02", "09", "10", "22", "25", "26", "31", "53", "91", "96", "97", "98",
})

# Excepciones por libro: tipos que sí tienen detalle en general pero no en un
# registro concreto (p. ej. boletas recibidas si el portal no tiene bandeja
# para ellas en compras). Vacío hasta que se confirme contra el portal.
SIN_DETALLE_POR_LIBRO: dict[str, frozenset[str]] = {
    "compras": frozenset(),
    "ventas": frozenset(),
}

# Documento de identidad genérico usado en boletas al público. Contasis escribe
# "1 / 11111111"; la descarga del SIRE trae "-" en ambos campos.
DOC_IDENTIDAD_GENERICO = "11111111"


def describe_comprobante(tipo_cp: str) -> str:
    return TIPO_COMPROBANTE.get(tipo_cp, f"DESCONOCIDO ({tipo_cp})")


def describe_doc_identidad(tipo_doc: str) -> str:
    return TIPO_DOC_IDENTIDAD.get(tipo_doc, f"DESCONOCIDO ({tipo_doc})")


def es_nota(tipo_cp: str) -> bool:
    return tipo_cp in TIPOS_NOTA_CREDITO or tipo_cp in TIPOS_NOTA_DEBITO
