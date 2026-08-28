import asyncio
import json
import logging

import numpy as np
from google import genai
from google.genai import types

from app.core.config import settings
from app.domain.comprobante import EstadoProcesamiento

logger = logging.getLogger(__name__)

vector_db: list[dict] = []

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY no está configurada en el entorno")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


async def cargar_vector(db) -> None:
    from app.repositories import vectores as repo_vectores

    global vector_db
    vector_db = await repo_vectores.cargar_global(db)
    logger.info("Vector global listo con %s chunks", len(vector_db))


def extraer_chunks_pdf(pdf_bytes: bytes, filename: str, max_chars: int = 1500) -> list[dict]:
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
      "confianza": "95% | 70% | 40%",
      "estado": "Analizado | Requiere revision humana",
      "documentos": true,
      "descripcion": "Resumen tecnico de la transaccion, maximo 80 palabras",
      "observaciones": "Observaciones tecnicas reales (Evita la palabra 'inferido' y justifica usando el rubro y los datos crudos)"
    }}

    INFORMACION DEL COMPROBANTE:
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


async def procesar_lote(
    db,
    empresa_id: str,
    periodo: str,
    vector_db_usuario=None,
    rubro: str = "General",
) -> dict:
    from app.repositories import comprobantes as repo_comprobantes
    from app.services.comprobante_service import texto_para_ia

    pendientes = await repo_comprobantes.listar_pendientes_analisis(db, empresa_id, periodo)

    if not pendientes:
        logger.info(
            "Análisis IA sin pendientes empresa_id=%s periodo=%s", empresa_id, periodo
        )
        return _build_result(0, [])

    async def analizar(documento) -> str:
        serie_numero = documento.get("serie_numero")
        documento_id = documento["_id"]

        extra = documento.get("extra") or {}
        if not extra.get("raw_sire") and not documento.get("detalle_sunat"):
            logger.warning(
                "Comprobante sin datos suficientes para analizar serie_numero=%s",
                serie_numero,
            )
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.SIN_DATOS
            )
            return "sin_datos"

        try:
            datos = await asyncio.to_thread(
                extraer_datos_factura,
                texto_para_ia(documento),
                vector_db_usuario,
                rubro,
            )
            await repo_comprobantes.guardar_analisis(
                db, documento_id, datos, EstadoProcesamiento.ANALIZADO
            )
            return "exito"
        except Exception:
            logger.exception(
                "Error analizando comprobante con Gemini serie_numero=%s", serie_numero
            )
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.ERROR_ANALISIS
            )
            return "error"

    logger.info(
        "Iniciando análisis IA empresa_id=%s periodo=%s comprobantes=%s",
        empresa_id,
        periodo,
        len(pendientes),
    )

    resultados = await asyncio.gather(*[analizar(documento) for documento in pendientes])
    resumen = _build_result(len(pendientes), list(resultados))

    logger.info(
        "Análisis IA finalizado empresa_id=%s periodo=%s total=%s procesadas=%s errores=%s sin_datos=%s",
        empresa_id,
        periodo,
        len(pendientes),
        resumen["procesadas"],
        resumen["errores"],
        resumen["sin_datos"],
    )
    return resumen
