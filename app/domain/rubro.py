from __future__ import annotations

import jwt

RUBRO_POR_DEFECTO = "General"
RUBRO_DESCONOCIDO = "Servicios Generales"

RUBROS_POR_PREFIJO_CIIU: dict[str, str] = {
    "01": "Agropecuario",
    "02": "Agropecuario",
    "03": "Agropecuario",
    "10": "Manufactura",
    "11": "Manufactura",
    "31": "Manufactura",
    "41": "Construcción",
    "42": "Construcción",
    "43": "Construcción",
    "45": "Comercio",
    "46": "Comercio",
    "47": "Comercio",
    "49": "Transporte",
    "50": "Transporte",
    "51": "Transporte",
    "55": "Restaurantes / Alimentación",
    "56": "Restaurantes / Alimentación",
    "62": "Tecnología / Informática",
    "64": "Finanzas",
    "65": "Finanzas",
    "66": "Finanzas",
    "69": "Servicios Profesionales",
    "70": "Servicios Profesionales",
    "71": "Servicios Profesionales",
    "85": "Educación",
    "86": "Salud",
    "87": "Salud",
    "88": "Salud",
}


def desde_ciiu(ciiu: str) -> str:
    if not ciiu:
        return RUBRO_POR_DEFECTO
    return RUBROS_POR_PREFIJO_CIIU.get(str(ciiu).strip()[:2], RUBRO_DESCONOCIDO)


def desde_token_sunat(token: str) -> str:
    if not token:
        return RUBRO_POR_DEFECTO
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        ciiu = (
            payload.get("userdata", {})
            .get("map", {})
            .get("ddpData", {})
            .get("ddp_ciiu", "")
        )
        return desde_ciiu(ciiu)
    except Exception:
        return RUBRO_POR_DEFECTO
