import re
import unicodedata

from app.domain.captura.models import Classification


def normalize(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text.upper()) if unicodedata.category(c) != "Mn"
    )


# Las menciones a documentos afectados puntúan menos que un título específico.
RULES = {
    "01": [("FACTURA ELECTRONICA", 9), ("FACTURA", 3)],
    "02": [("RECIBO POR HONORARIOS", 12)],
    "03": [("BOLETA DE VENTA", 12), ("BOLETA ELECTRONICA", 10)],
    "07": [("NOTA DE CREDITO", 18)],
    "08": [("NOTA DE DEBITO", 18)],
    "09": [("GUIA DE REMISION REMITENTE", 14)],
    "10": [("RECIBO POR ARRENDAMIENTO", 14)],
    "13": [("DOCUMENTO AUTORIZADO SBS", 12)],
    "14": [("SUMINISTRO", 4), ("CONSUMO KWH", 8), ("RECIBO DE AGUA", 12)],
    "18": [("APORTE AFP", 12)],
    "19": [("BOLETO DE ESPECTACULO", 12)],
    "22": [("OPERACIONES NO HABITUALES", 12)],
    "23": [("POLIZA DE ADJUDICACION", 12)],
    "25": [("DOCUMENTO DE ATRIBUCION", 12)],
    "26": [("AGUA CON FINES AGRARIOS", 12)],
    "29": [("COFOPRI", 12)],
    "30": [("DOCUMENTO ADQUIRENTE TARJETAS", 12)],
    "31": [("GUIA DE REMISION TRANSPORTISTA", 14)],
    "34": [("DOCUMENTO DEL OPERADOR", 12)],
    "35": [("DOCUMENTO DEL PARTICIPE", 12)],
    "36": [("RECIBO DISTRIBUCION GAS NATURAL", 12)],
    "42": [("DOCUMENTO TARJETAS PROPIAS", 12)],
    "53": [("DECLARACION MENSAJERIA COURIER", 12)],
    "64": [("SERVICIOS RELACIONADOS CON TRANSPORTE AEREO", 12)],
    "87": [("NOTA DE CREDITO ESPECIAL", 25)],
    "88": [("NOTA DE DEBITO ESPECIAL", 25)],
    "91": [("COMPROBANTE NO DOMICILIADO", 14)],
    "96": [("EXCESO CREDITO FISCAL RETIRO", 14)],
    "97": [("NOTA DE CREDITO NO DOMICILIADO", 25)],
    "98": [("NOTA DE DEBITO NO DOMICILIADO", 25)],
    "YAPE_TRANSFER": [("YAPEASTE", 12), ("YAPE", 4)],
    "YAPE_SERVICE_PAYMENT": [("YAPE", 5), ("PAGO DE SERVICIO", 12)],
    "PLIN_TRANSFER": [("PLIN", 12)],
    "BANK_TRANSFER": [("TRANSFERENCIA EXITOSA", 12), ("TRANSFERENCIA BANCARIA", 12)],
    "POS_VOUCHER": [("APROBADA", 4), ("VISA", 3), ("MASTERCARD", 3), ("TERMINAL", 4)],
    "CASH_DEPOSIT": [("DEPOSITO EN EFECTIVO", 12)],
    "DAILY_SETTLEMENT": [("LIQUIDACION DIARIA", 12), ("CIERRE DE LOTE", 10)],
}
NAMES = {
    "01": "FACTURA",
    "02": "HONORARIOS",
    "03": "BOLETA",
    "07": "NOTA_CREDITO",
    "08": "NOTA_DEBITO",
    "09": "GUIA_REMITENTE",
    "14": "SERVICIO_PUBLICO",
    "31": "GUIA_TRANSPORTISTA",
}


def classify(text: str) -> Classification:
    normalized = normalize(text)
    scores = {
        kind: sum(
            weight
            for term, weight in rules
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized)
        )
        for kind, rules in RULES.items()
    }
    if "YAPE" not in normalized:
        scores["YAPE_SERVICE_PAYMENT"] = 0
    ranking = sorted(scores, key=lambda key: scores[key], reverse=True)
    winner, second = ranking[:2]
    if scores[winner] < 7 or scores[winner] == scores[second]:
        return Classification()
    sunat = winner if winner.isdigit() else None
    return Classification(
        family="TAX" if sunat else "PAYMENT",
        type=NAMES.get(winner, winner),
        sunat_code=sunat,
        confidence=min(0.99, 0.7 + (scores[winner] - scores[second]) / 60),
    )
