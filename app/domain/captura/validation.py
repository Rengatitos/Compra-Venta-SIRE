import hashlib
from decimal import Decimal

from app.domain.captura.models import ExtractedDocument


def valid_ruc(value: str) -> bool:
    if len(value) != 11 or not value.isdigit():
        return False
    check = (
        11
        - sum(int(n) * w for n, w in zip(value[:10], (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True))
        % 11
    )
    return int(value[-1]) == (0 if check == 10 else 1 if check == 11 else check)


def validate(document: ExtractedDocument) -> list[dict]:
    results = []
    values = {key: field.value for key, field in document.fields.items()}

    def add(rule: str, status: str) -> None:
        results.append({"rule": rule, "status": status})

    if document.classification.type == "UNKNOWN":
        add("CLASSIFICATION", "WARNING")
    if document.classification.family == "TAX":
        ruc = values.get("issuer.ruc")
        add("ISSUER_RUC", "PASS" if ruc and valid_ruc(ruc) else "FAIL" if ruc else "WARNING")
        add(
            "SERIES_NUMBER",
            "PASS"
            if values.get("document.series") and values.get("document.number")
            else "WARNING",
        )
    total = values.get("amounts.total")
    add("POSITIVE_TOTAL", "PASS" if total and Decimal(total) > 0 else "FAIL")
    add(
        "CURRENCY",
        "PASS" if values.get("document.currency") in {"PEN", "USD", "EUR"} else "WARNING",
    )
    base, igv = values.get("amounts.subtotal"), values.get("amounts.igv")
    if all(value is not None for value in (base, igv, total)):
        add(
            "TOTAL_ARITHMETIC",
            "PASS"
            if abs(Decimal(base) + Decimal(igv) - Decimal(total)) <= Decimal(".05")
            else "FAIL",
        )
    for key, field in document.fields.items():
        if field.status == "ILLEGIBLE":
            add(f"ILLEGIBLE:{key}", "WARNING")
    for index, item in enumerate(document.items):
        quantity, price, amount = (item[key].value for key in ("quantity", "unit_price", "total"))
        if all(value is not None for value in (quantity, price, amount)):
            delta = abs(Decimal(quantity) * Decimal(price) - Decimal(amount))
            add(f"ITEM_ARITHMETIC:{index}", "PASS" if delta <= Decimal(".05") else "FAIL")
    if document.items and total and all(item["total"].value for item in document.items):
        items_total = sum(Decimal(item["total"].value) for item in document.items)
        add(
            "ITEMS_TOTAL",
            "PASS" if abs(items_total - Decimal(total)) <= Decimal(".05") else "WARNING",
        )
    return results


def fingerprint(document: ExtractedDocument) -> str | None:
    keys = (
        "issuer.ruc",
        "document.series",
        "document.number",
        "document.issue_date",
        "amounts.total",
    )
    values = [document.fields[key].value for key in keys]
    if not all(values) or document.classification.family != "TAX":
        return None
    text = "|".join([document.classification.type, *map(str, values)])
    return hashlib.sha256(text.encode()).hexdigest()


def match_score(left: dict, right: dict) -> int:
    """Campos ausentes nunca cuentan como coincidencias."""

    def value(doc: dict, key: str):
        return doc.get("extracted", {}).get("fields", {}).get(key, {}).get("value")

    if left.get("family") == right.get("family") or "PAYMENT" not in {
        left.get("family"),
        right.get("family"),
    }:
        return 0
    currency = value(left, "document.currency")
    if not currency or currency != value(right, "document.currency"):
        return 0
    total = value(left, "amounts.total")
    other = value(right, "amounts.total")
    score = 50 if total and other and abs(Decimal(total) - Decimal(other)) <= Decimal(".01") else 0
    if left.get("document_date") and left.get("document_date") == right.get("document_date"):
        score += 20
    merchant = value(left, "issuer.name") or value(left, "payment.merchant")
    other_merchant = value(right, "issuer.name") or value(right, "payment.merchant")
    if merchant and other_merchant and merchant.casefold() == other_merchant.casefold():
        score += 20
    time, other_time = value(left, "document.issue_time"), value(right, "document.issue_time")
    if time and other_time and time == other_time:
        score += 10
    return score
