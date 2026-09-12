"""Repara secuencias UTF-8 interpretadas como Latin-1 o Windows-1252."""

import re


_SECUENCIA = re.compile(r"[ÃÂ][\u0080-\u00bf€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]")


def corregir_codificacion(texto: str) -> str:
    def reparar(coincidencia: re.Match) -> str:
        fragmento = coincidencia.group()
        for encoding in ("latin-1", "cp1252"):
            try:
                return fragmento.encode(encoding).decode("utf-8")
            except UnicodeError:
                pass
        return fragmento

    # También admite texto que pasó dos veces por una decodificación incorrecta.
    for _ in range(3):
        corregido = _SECUENCIA.sub(reparar, texto)
        if corregido == texto:
            break
        texto = corregido
    return texto
