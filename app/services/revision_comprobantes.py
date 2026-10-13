import re

from app.services.sunat.campos import raw_sire
from app.services.sunat.contraparte import vacio


def de_baja(documento):
    """Estado BAJA de la propuesta SUNAT; nunca se infiere de sus importes."""
    if documento.get('origen') != 'sire':
        return False
    # La respuesta serializada conserva la marca aunque ya no lleve `extra`.
    if documento.get('de_baja_sunat') is True:
        return True
    extra = documento.get('extra')
    extra = extra if isinstance(extra, dict) else {}
    crudo = raw_sire(documento)
    return any(str(valor).strip() == '2' for valor in (
        extra.get('estado_comprobante'), crudo.get('codEstadoComprobante'),
    )) or any(str(valor).strip().upper() == 'BAJA' for valor in (
        extra.get('descripcion_estado_comprobante'), crudo.get('desEstadoComprobante'),
    ))


def anulado(documento):
    return de_baja(documento) or (documento.get('origen') == 'sire' and any(
        isinstance(item, dict)
        and re.search(r'\banulad[oa]s?\b', str(item.get('descripcion') or ''), re.I)
        for item in documento.get('detalle_sunat') or []
    ))


def incompleto(documento):
    intentado = (
        documento.get('glosa_consultada') or documento.get('contraparte_sunat_consultada')
        or documento.get('detalle_sunat')
    )
    return bool(intentado and not anulado(documento) and any(
        vacio(documento.get(campo)) for campo in ('razon_social', 'documento_contraparte')
    ))
