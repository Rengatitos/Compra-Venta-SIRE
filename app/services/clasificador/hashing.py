from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def stable_id(*parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()
