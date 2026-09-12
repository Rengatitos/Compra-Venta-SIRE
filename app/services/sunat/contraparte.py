"""Datos explícitos del receptor, sin inferencias ni sustitución de datos SIRE."""

VACIOS = {"", "-", "—", "0"}


def vacio(valor) -> bool:
    return str(valor or "").strip() in VACIOS


def receptor_listado(fila: dict) -> dict[str, str]:
    documento = str(fila.get("nroRucReceptor") or "").strip()
    tipo = str(fila.get("codTipoDocReceptor") or "").strip().lstrip("0")
    nombre = str(fila.get("nroRucReceptorDesc") or "").strip()
    prefijo, separador, resto = nombre.partition(" - ")
    datos = {}
    if separador and prefijo.strip() == documento and not vacio(resto):
        datos["razon_social"] = resto.strip()
    if not vacio(documento):
        datos["documento_contraparte"] = documento
        if tipo:
            datos["tipo_doc_identidad"] = tipo
    return datos


def receptor_html(filas: list[list[str]]) -> dict[str, str]:
    datos = {}
    tipos = {"DNI": "1", "RUC": "6", "CARNET DE EXTRANJERIA": "4", "PASAPORTE": "7"}
    for fila in filas:
        if len(fila) != 3 or fila[1].strip() != ":":
            continue
        etiqueta, valor = fila[0].strip().upper(), fila[2].strip()
        if vacio(valor):
            continue
        if etiqueta in {"SEÑOR(ES)", "SEÑOR (ES)"}:
            datos["razon_social"] = valor
        elif etiqueta in tipos:
            datos["documento_contraparte"] = valor
            datos["tipo_doc_identidad"] = tipos[etiqueta]
    return datos


def completar(documento: dict) -> dict:
    salida = dict(documento)
    datos = documento.get("contraparte_sunat") or {}
    if documento.get("libro") != "ventas":
        return salida
    # No combinar el tipo de un documento diferente con el documento de SIRE.
    compatible = vacio(documento.get("documento_contraparte")) or (
        str(documento.get("documento_contraparte")).strip() == datos.get("documento_contraparte")
    )
    for campo in ("razon_social", "documento_contraparte", "tipo_doc_identidad"):
        if vacio(salida.get(campo)) and not vacio(datos.get(campo)):
            if campo == "tipo_doc_identidad" and not compatible:
                continue
            salida[campo] = datos[campo]
    return salida
