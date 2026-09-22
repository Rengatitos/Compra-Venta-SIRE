import re


class SensitiveDataMasker:
    """Conserva last4 de tarjetas; los logs usan exclusivamente IDs técnicos."""

    @staticmethod
    def cards(text: str) -> str:
        return re.sub(
            r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)",
            lambda match: "************" + re.sub(r"\D", "", match[0])[-4:],
            text,
        )

    @staticmethod
    def log(text: str) -> str:
        return re.sub(r"\b\d{7,}\b", "[REDACTED]", SensitiveDataMasker.cards(text))
