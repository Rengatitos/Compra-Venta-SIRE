import asyncio
import json
import logging
import os

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types


load_dotenv()

logger = logging.getLogger(__name__)

# Embedding global (PCGE)
vector_db: list[dict] = []

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Construye el cliente Gemini de forma perezosa (al primer uso, no al importar el módulo).

    Antes se construía a nivel de módulo: si faltaba GEMINI_API_KEY, el import
    de todo el paquete de rutas fallaba en seco en vez de fallar solo al usarse.
    """
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


async def cargar_vector(col) -> None:
    """Carga embedding desde la colección global de MongoDB."""
    from app.services.vector_store import cargar_global_en_memoria

    global vector_db
    vector_db = await cargar_global_en_memoria(col)
    logger.info("vector listo con %s chunks", len(vector_db))


def extraer_chunks_pdf(pdf_bytes: bytes, filename: str, max_chars: int = 1500) -> list[dict]:
    """
    Extrae texto de un PDF en memoria y lo divide en chunks para embeddings.
    """
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks = []
        for num_pagina, pagina in enumerate(doc, start=1):
            texto = pagina.get_text("text").strip()
            if not texto:
                continue

            if len(texto) <= max_chars:
                chunks.append(
                    {
                        "texto": texto,
                        "metadata": {"documento": filename, "pagina": num_pagina},
                    }
                )
                continue

            parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
            buffer = ""
            for parrafo in parrafos:
                if len(buffer) + len(parrafo) <= max_chars:
                    buffer += parrafo + "\n\n"
                    continue

                if buffer.strip():
                    chunks.append(
                        {
                            "texto": buffer.strip(),
                            "metadata": {"documento": filename, "pagina": num_pagina},
                        }
                    )
                buffer = parrafo + "\n\n"

            if buffer.strip():
                chunks.append(
                    {
                        "texto": buffer.strip(),
                        "metadata": {"documento": filename, "pagina": num_pagina},
                    }
                )

        doc.close()
        return chunks
    except Exception:
        logger.exception("Error extrayendo chunks de PDF=%s", filename)
        return []


def generar_embeddings_pdf(chunks: list[dict]) -> list[dict]:
    """
    Genera embeddings para los chunks extraidos de PDFs de referencia.
    """
    resultado = []
    for chunk in chunks:
        try:
            respuesta = _get_client().models.embed_content(
                model="models/gemini-embedding-001",
                contents=chunk["texto"],
            )
            resultado.append(
                {
                    "texto": chunk["texto"],
                    "metadata": chunk["metadata"],
                    "embedding": respuesta.embeddings[0].values,
                }
            )
        except Exception:
            logger.exception(
                "Error generando embedding para documento=%s pagina=%s",
                chunk.get("metadata", {}).get("documento"),
                chunk.get("metadata", {}).get("pagina"),
            )
    return resultado


def buscar_contexto(texto, vector_db_usuario=None, top_k=20):
    if not vector_db and not vector_db_usuario:
        return "No hay normativas contables disponibles."

    try:
        respuesta = _get_client().models.embed_content(
            model="models/gemini-embedding-001",
            contents=texto,
        )
        pregunta = (
            np.array(respuesta.embeddings[0].values)
            if hasattr(respuesta, "embeddings")
            else respuesta
        )

        lineas = []

        if vector_db:
            resultados = []
            for item in vector_db:
                emb_db = np.array(item["embedding"])
                score = np.dot(pregunta, emb_db) / (
                    np.linalg.norm(pregunta) * np.linalg.norm(emb_db)
                )
                resultados.append((score, item))

            resultados.sort(key=lambda x: x[0], reverse=True)
            lineas.append("CONTEXTO BASE DEL SISTEMA")
            lineas.extend(
                [
                    f"[{r['metadata'].get('documento', '')}] {r['texto']}"
                    for _, r in resultados[:top_k]
                ]
            )

        if vector_db_usuario:
            resultados_usuario = []
            for item in vector_db_usuario:
                emb_db = np.array(item["embedding"])
                score = np.dot(pregunta, emb_db) / (
                    np.linalg.norm(pregunta) * np.linalg.norm(emb_db)
                )
                resultados_usuario.append((score, item))

            resultados_usuario.sort(key=lambda x: x[0], reverse=True)
            lineas.append("\nCONTEXTO ADICIONAL DEL USUARIO")
            lineas.extend(
                [
                    f"[{r['metadata'].get('documento', '')}] {r['texto']}"
                    for _, r in resultados_usuario[:top_k]
                ]
            )

        return "\n".join(lineas)
    except Exception:
        logger.exception("Error procesando busqueda de contexto para Gemini")
        return ""


def extraer_datos_factura(texto_factura: str, vector_db_usuario=None, rubro: str = "General"):
    contexto = buscar_contexto(texto_factura, vector_db_usuario=vector_db_usuario)

    instruccion_referencias = ""
    if vector_db_usuario:
        instruccion_referencias = """
    REGLA ADICIONAL:
    Tambien cuentas con documentos PDF subidos por el usuario.
    Si aportan contexto util, usalos para reforzar la clasificacion y mencionarlo en observaciones.
    """

    prompt = f"""
    Eres un analista contable experto especializado en el rubro: {rubro}.
    Tu mision es clasificar contablemente la factura basandote en TODOS los datos en crudo (JSON) proporcionados.

    REGLAS SOBRE LA SERIE DE LA FACTURA:
    - Serie F (ej. F001): Factura fisica o electronica estandar. Suele representar compras de bienes o servicios empresariales.
    - Serie E (ej. E001): Representa facturaciones por recibos por honorarios o similares. Suelen ser gastos o costos directos por prestacion de servicios profesionales.

    ESTRATEGIA DE ANALISIS:
    - Analiza minuciosamente TODOS los campos disponibles en la informacion cruda (RAW_DATA). 
    - No te limites al nombre del proveedor. Considera los montos, impuestos, tipo de operacion, moneda y cualquier otro dato relevante en el JSON.
    - Contextualiza tu decision basandote estrictamente en cómo afecta este gasto/costo al rubro de la empresa auditora ({rubro}).
    - NUNCA uses frases como "Clasificacion inferida por el nombre del proveedor" o "Asumiendo por...". Brinda una justificacion tecnica real basada en la combinacion de los datos proporcionados.
    
    {instruccion_referencias}

    CONTEXTO NORMATIVO (PCGE):
    {contexto}

    FORMATO DE SALIDA (JSON ESTRICTO):
    {{
      "detalle": [
        {{
          "producto": "Nombre del item comprado o descripcion basada en la operacion",
          "categoria_contable": "Nombre de la categoria contable sugerida",
          "cantidad": "Cantidad (si esta disponible, si no '1')",
          "importe": "Monto de la operacion",
          "razon": "Justificacion tecnica del gasto/costo"
        }}
      ],
      "cuenta_contable": "Codigo PCGE",
      "centro_costos": "Centro de costos sugerido",
      "condicion_igv": "Gravado | Exonerado | Inafecto",
      "resultado": "COSTO | GASTO | ACTIVO | NO DETERMINADO",
      "ia_confidence": "95% | 70% | 40%",
      "ia_status": "Analizado | Requiere revision humana",
      "Documentos": true,
      "Descripcion": "Resumen tecnico de la transaccion, maximo 80 palabras",
      "Observaciones": "Observaciones tecnicas reales (Evita la palabra 'inferido' y justifica usando el rubro y los datos crudos)"
    }}

    INFORMACION CRUDA DE LA FACTURA:
    """

    response_json = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt, texto_factura],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return json.loads(response_json.text)


def _build_result(total_encontradas: int, resultados: list[str]):
    return {
        "total_encontradas": total_encontradas,
        "procesadas": resultados.count("exito"),
        "errores": resultados.count("error"),
        "sin_datos": resultados.count("sin_datos"),
        "resultados": resultados,
    }


async def procesar_lote_extracciones(
    user_id: str,
    periodo: str,
    db,
    vector_db_usuario=None,
    rubro: str = "General",
):
    facturas_col = db["facturas"]

    cursor = facturas_col.find(
        {
            "user_id": user_id,
            "periodo": periodo,
            "$or": [
                {"estado_procesamiento": "sire_recibido"},
                {"estado_procesamiento": "error_analisis"},
                {"estado_procesamiento": {"$exists": False}},
                {"estado_procesamiento": ""},
            ],
        }
    ).sort([("_id", -1)])

    facturas_pendientes_raw = await cursor.to_list(length=1000)

    # Evita doble analisis cuando existen duplicados historicos por serie_numero.
    facturas_pendientes = []
    series_vistas = set()
    duplicadas = 0
    for row in facturas_pendientes_raw:
        serie_num = row.get("serie_numero")
        key = serie_num if serie_num else str(row.get("_id"))
        if key in series_vistas:
            duplicadas += 1
            continue
        series_vistas.add(key)
        facturas_pendientes.append(row)

    if duplicadas:
        logger.warning(
            "Analisis IA detecto duplicados user_id=%s periodo=%s duplicadas_omitidas=%s",
            user_id,
            periodo,
            duplicadas,
        )

    if not facturas_pendientes:
        logger.info("Analisis IA sin pendientes user_id=%s periodo=%s", user_id, periodo)
        return _build_result(0, [])

    async def analizar_y_actualizar_factura(row):
        serie_num = row.get("serie_numero")
        raw_data = row.get("raw_data", "")
        factura_id = row["_id"]


        try:
            if not raw_data or len(str(raw_data)) < 10:
                logger.warning("Factura sin datos suficientes para analisis serie_numero=%s", serie_num)
                await facturas_col.update_one(
                    {"_id": factura_id},
                    {"$set": {"estado_procesamiento": "sin_datos"}},
                )
                return "sin_datos"

            # Enriquecer con el detalle real de SUNAT si está disponible
            detalle_sunat = row.get("detalle_compras_sunat")
            texto_para_ia = str(raw_data)
            if detalle_sunat:
                lineas_detalle = "\n".join(
                    f"- Cant: {item.get('cantidad','')} {item.get('unidad_medida','')} | "
                    f"Descripcion: {item.get('descripcion','')} | "
                    f"V.Unit: {item.get('valor_unitario','')} | "
                    f"P.Unit: {item.get('precio_unitario','')} | "
                    f"Total: {item.get('valor_venta','')}"
                    for item in detalle_sunat
                )
                texto_para_ia = (
                    f"{texto_para_ia}\n\n"
                    f"DETALLE REAL DE LOS ITEMS (extraido de SUNAT):\n{lineas_detalle}"
                )

            datos_procesados = await asyncio.to_thread(
                extraer_datos_factura,
                texto_para_ia,
                vector_db_usuario,
                rubro,
            )
            datos_procesados["_ID_REFERENCIA"] = serie_num

            await facturas_col.update_one(
                {"_id": factura_id},
                {
                    "$set": {
                        "metadata_procesada": datos_procesados,
                        "estado_procesamiento": "analizado",
                    }
                },
            )

            return "exito"

        except Exception:
            logger.exception("Error procesando factura mediante Gemini serie_numero=%s", serie_num)
            await facturas_col.update_one(
                {"_id": factura_id},
                {"$set": {"estado_procesamiento": "error_analisis"}},
            )
            return "error"

    logger.info(
        "Iniciando analisis IA user_id=%s periodo=%s facturas=%s",
        user_id,
        periodo,
        len(facturas_pendientes),
    )

    resultados = await asyncio.gather(
        *[analizar_y_actualizar_factura(row) for row in facturas_pendientes]
    )

    resumen = _build_result(len(facturas_pendientes), resultados)

    logger.info(
        "Analisis IA finalizado user_id=%s periodo=%s total=%s procesadas=%s errores=%s sin_datos=%s",
        user_id,
        periodo,
        len(facturas_pendientes),
        resumen["procesadas"],
        resumen["errores"],
        resumen["sin_datos"],
    )
    return resumen
