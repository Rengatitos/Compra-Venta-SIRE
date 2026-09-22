import hashlib
from datetime import date, time
from decimal import Decimal, InvalidOperation

from app.domain.captura.classification import normalize
from app.domain.captura.models import ExtractedDocument


def valid_ruc(value: str) -> bool:
    if not isinstance(value, str) or len(value) != 11 or not value.isascii() or not value.isdigit():
        return False
    check = (
        11
        - sum(int(n) * w for n, w in zip(value[:10], (5, 4, 3, 2, 7, 6, 5, 4, 3, 2), strict=True))
        % 11
    )
    return int(value[-1]) == (0 if check == 10 else 1 if check == 11 else check)


def decimal_value(value) -> Decimal | None:
    """Los datos OCR o corregidos inválidos generan revisión, nunca una excepción."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number.copy_abs() <= Decimal("1e12") else None
    except (InvalidOperation, ValueError, TypeError):
        return None


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
    total = decimal_value(values.get("amounts.total"))
    add("POSITIVE_TOTAL", "PASS" if total is not None and total > 0 else "FAIL")
    add(
        "CURRENCY",
        "PASS" if values.get("document.currency") in {"PEN", "USD", "EUR"} else "WARNING",
    )
    numeric = {
        key: decimal_value(value)
        for key, value in values.items()
        if key.startswith(("amounts.", "honorarios."))
    }
    for key, number in numeric.items():
        if values[key] is not None and number is None:
            add(f"NUMERIC:{key}", "FAIL")
    base, igv = numeric.get("amounts.subtotal"), numeric.get("amounts.igv")
    discount = numeric.get("amounts.discount")
    taxes = numeric.get("amounts.other_taxes")
    extras_valid = all(
        values.get(key) is None or numeric.get(key) is not None
        for key in ("amounts.discount", "amounts.other_taxes")
    )
    if all(value is not None for value in (base, igv, total)) and extras_valid:
        add(
            "TOTAL_ARITHMETIC",
            "PASS"
            if abs(base + igv + (taxes or 0) - (discount or 0) - total) <= Decimal(".05")
            else "FAIL",
        )
    for key, field in document.fields.items():
        if field.status == "ILLEGIBLE":
            add(f"ILLEGIBLE:{key}", "WARNING")
    for index, item in enumerate(document.items):
        quantity, price, amount, discount = (
            decimal_value(item[key].value) if key in item else None
            for key in ("quantity", "unit_price", "total", "discount")
        )
        discount_present = "discount" in item and item["discount"].value is not None
        for key, field in item.items():
            if field.status == "ILLEGIBLE":
                add(f"ILLEGIBLE:items.{index}.{key}", "WARNING")
        if any(value is None for value in (quantity, price, amount)):
            add(f"ITEM_ARITHMETIC:{index}", "WARNING")
        elif discount_present and discount is None:
            add(f"ITEM_ARITHMETIC:{index}", "FAIL")
        elif quantity <= 0 or price < 0 or amount < 0 or (discount is not None and discount < 0):
            add(f"ITEM_ARITHMETIC:{index}", "FAIL")
        else:
            delta = abs(quantity * price - (discount or 0) - amount)
            add(f"ITEM_ARITHMETIC:{index}", "PASS" if delta <= Decimal(".05") else "FAIL")
    item_totals = [
        decimal_value(item["total"].value) if "total" in item else None
        for item in document.items
    ]
    if item_totals and total is not None and all(value is not None for value in item_totals):
        items_total = sum(item_totals)
        add(
            "ITEMS_TOTAL",
            "PASS" if abs(items_total - total) <= Decimal(".05") else "WARNING",
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
    values = [document.fields[key].value if key in document.fields else None for key in keys]
    if not all(values) or document.classification.family != "TAX":
        return None
    text = "|".join([document.classification.type, *map(str, values)])
    return hashlib.sha256(text.encode()).hexdigest()


def match_score(left: dict, right: dict) -> int:
    """Campos ausentes nunca cuentan como coincidencias."""

    def value(doc: dict, key: str):
        return doc.get("extracted", {}).get("fields", {}).get(key, {}).get("value")

    if {
        left.get("family"),
        right.get("family"),
    } != {"TAX", "PAYMENT"}:
        return 0
    currency = value(left, "document.currency")
    if not currency or currency != value(right, "document.currency"):
        return 0
    total = decimal_value(value(left, "amounts.total"))
    other = decimal_value(value(right, "amounts.total"))
    score = (
        50 if total is not None and other is not None and total > 0 and other > 0
        and abs(total - other) <= Decimal(".01") else 0
    )
    try:
        same_date = date.fromisoformat(left.get("document_date") or "") == date.fromisoformat(
            right.get("document_date") or ""
        )
    except (ValueError, TypeError):
        same_date = False
    if same_date:
        score += 20
    merchant = value(left, "issuer.name") or value(left, "payment.merchant")
    other_merchant = value(right, "issuer.name") or value(right, "payment.merchant")
    if (
        isinstance(merchant, str) and isinstance(other_merchant, str)
        and merchant.strip() and normalize(merchant).split() == normalize(other_merchant).split()
    ):
        score += 20
    if same_date:
        try:
            left_time = time.fromisoformat(value(left, "document.issue_time") or "")
            right_time = time.fromisoformat(value(right, "document.issue_time") or "")
            # La ventana de cinco minutos solo aplica con la misma fecha documentada.
            left_seconds = left_time.hour * 3600 + left_time.minute * 60 + left_time.second
            right_seconds = right_time.hour * 3600 + right_time.minute * 60 + right_time.second
            if abs(left_seconds - right_seconds) <= 300:
                score += 10
        except (ValueError, TypeError):
            pass
    return score
