import re

from app.services.sunat.contraparte import vacio


def anulado(documento):
    return documento.get('origen') == 'sire' and any(
        isinstance(item, dict) and re.search(r'\banulad[oa]s?\b', str(item.get('descripcion') or ''), re.I)
        for item in documento.get('detalle_sunat') or []
    )


def incompleto(documento):
    intentado = documento.get('glosa_consultada') or documento.get('contraparte_sunat_consultada') or documento.get('detalle_sunat')
    return bool(intentado and not anulado(documento) and any(
        vacio(documento.get(campo)) for campo in ('razon_social', 'documento_contraparte')
    ))
