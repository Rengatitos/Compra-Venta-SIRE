from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9áéíóúüñ]+", re.IGNORECASE)


def normalize_for_search(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return " ".join(text.lower().split())


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(normalize_for_search(text))


def split_text(text: str, max_chars: int = 1400, overlap_chars: int = 180) -> list[str]:
    text = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        if end < n:
            cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end), text.rfind(" ", start, end))
            if cut > start + max_chars // 2:
                end = cut + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(start + 1, end - overlap_chars)
    return chunks


def compact_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def join_nonempty(parts: Iterable[str], sep: str = " | ") -> str:
    return sep.join(p for p in parts if p)
