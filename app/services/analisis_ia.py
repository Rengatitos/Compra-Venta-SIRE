from __future__ import annotations

import logging
from typing import Any
import re
from pathlib import Path

import fitz
import numpy as np

from app.domain.comprobante import EstadoProcesamiento
from app.services import ollama_rag

logger = logging.getLogger(__name__)
vector_db: list[dict[str, Any]] = []
from app.core.config import settings
from app.domain.comprobante import EstadoProcesamiento, Libro

logger = logging.getLogger(__name__)

vector_db: list[dict] = []

_client: genai.Client | None = None

# Espaciamos las llamadas y reintentamos con backoff para no saturar la cuota
# cuando se analizan varios comprobantes en el mismo lote. El intervalo viene
# de la configuración porque el techo depende del proveedor: AI Studio en tier
# gratuito da 5 req/min, Vertex bastante más.
GEMINI_MIN_INTERVAL_SECONDS = settings.GEMINI_MIN_INTERVAL_SECONDS
GEMINI_MAX_REINTENTOS = 3

# Vertex y AI Studio nombran los modelos distinto: AI Studio quiere el prefijo
# "models/" en los de embedding y Vertex los rechaza con ese prefijo.
_USANDO_VERTEX = bool(settings.VERTEX_PROJECT)
MODELO_EMBEDDING = (
    "gemini-embedding-001" if _USANDO_VERTEX else "models/gemini-embedding-001"
)
MODELO_TEXTO = "gemini-3.6-flash"

_gemini_lock = asyncio.Lock()
_gemini_ultima_llamada = 0.0


async def _esperar_turno_gemini() -> None:
    global _gemini_ultima_llamada
    async with _gemini_lock:
        loop = asyncio.get_event_loop()
        ahora = loop.time()
        espera = _gemini_ultima_llamada + GEMINI_MIN_INTERVAL_SECONDS - ahora
        if espera > 0:
            await asyncio.sleep(espera)
        _gemini_ultima_llamada = loop.time()


def _extraer_retry_delay(exc: APIError) -> float | None:
    detalles = exc.details if isinstance(exc.details, dict) else {}
    for item in detalles.get("error", {}).get("details", []):
        retry_delay = item.get("retryDelay")
        if retry_delay:
            match = re.match(r"([\d.]+)", retry_delay)
            if match:
                return float(match.group(1))
    return None


def _credenciales_vertex():
    if not settings.VERTEX_CREDENTIALS_FILE:
        # Sin fichero explícito dejamos que google-auth resuelva las
        # credenciales del entorno (GOOGLE_APPLICATION_CREDENTIALS, gcloud...).
        return None

    from google.oauth2 import service_account

    ruta = Path(settings.VERTEX_CREDENTIALS_FILE)
    if not ruta.is_absolute():
        # Las rutas del .env se escriben relativas a la raíz del proyecto, no
        # al directorio desde el que se arrancó uvicorn.
        ruta = Path(__file__).resolve().parents[2] / ruta
    if not ruta.is_file():
        raise RuntimeError(
            f"VERTEX_CREDENTIALS_FILE apunta a un fichero que no existe: {ruta}"
        )

    return service_account.Credentials.from_service_account_file(
        str(ruta), scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if _USANDO_VERTEX:
            _client = genai.Client(
                vertexai=True,
                project=settings.VERTEX_PROJECT,
                location=settings.VERTEX_LOCATION,
                credentials=_credenciales_vertex(),
            )
            logger.info(
                "Cliente Gemini vía Vertex AI (project=%s location=%s)",
                settings.VERTEX_PROJECT,
                settings.VERTEX_LOCATION,
            )
        else:
            if not settings.GEMINI_API_KEY:
                raise RuntimeError(
                    "Configura GEMINI_API_KEY o VERTEX_PROJECT en el entorno"
                )
            _client = genai.Client(api_key=settings.GEMINI_API_KEY)
            logger.info("Cliente Gemini vía API de AI Studio")
    return _client


async def cargar_vector(db) -> None:
    from app.repositories import vectores

    global vector_db
    vector_db = await vectores.cargar_global(db)
    logger.info("Vector global Ollama listo con %s chunks", len(vector_db))


def extraer_chunks_pdf(pdf_bytes: bytes, filename: str, max_chars: int = 1500) -> list[dict]:
    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
        chunks = []
        for pagina_numero, pagina in enumerate(documento, start=1):
            texto = pagina.get_text("text").strip()
            for inicio in range(0, len(texto), max_chars):
                fragmento = texto[inicio : inicio + max_chars].strip()
                if fragmento:
                    chunks.append(
                        {
                            "texto": fragmento,
                            "metadata": {"documento": filename, "pagina": pagina_numero},
                        }
                    )
        documento.close()
        return chunks
    except Exception:
        logger.exception("Error extrayendo texto de %s", filename)
        return []


def generar_embeddings_pdf(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []
    vectores = ollama_rag.embed_documents([chunk["texto"] for chunk in chunks])
    return [
        {"texto": c["texto"], "metadata": c["metadata"], "embedding": v}
        for c, v in zip(chunks, vectores, strict=True)
    ]


def buscar_contexto(texto: str, vector_db_usuario=None, top_k: int = 20) -> str:
    candidatos = [*(vector_db or []), *(vector_db_usuario or [])]
    if not candidatos:
        return "No hay referencias PDF disponibles."
    pregunta = np.asarray(ollama_rag.embed_query(texto))
    resultados = []
    for item in candidatos:
        vector = np.asarray(item.get("embedding") or [])
        if vector.size != pregunta.size or not vector.size:
            continue
        divisor = np.linalg.norm(pregunta) * np.linalg.norm(vector)
        resultados.append((float(np.dot(pregunta, vector) / divisor) if divisor else 0, item))
    resultados.sort(key=lambda par: par[0], reverse=True)
    return "\n".join(
        f"[{i.get('metadata', {}).get('documento', '')}] {i.get('texto', '')}"
        for _, i in resultados[:top_k]
    )


async def procesar_lote(
    db, empresa: dict, periodo: str, vector_db_usuario=None, rubro: str = "General"
) -> dict:
    from app.repositories import comprobantes as repo_comprobantes

    pendientes = await repo_comprobantes.listar_pendientes_analisis(
        db, str(empresa["_id"]), periodo
    )
    resultados: list[str] = []
    for documento in pendientes:
        documento_id = documento["_id"]
        if not (documento.get("extra") or {}).get("raw_sire") and not documento.get(
            "detalle_sunat"
        ):
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.SIN_DATOS
    resultado = []
    for chunk in chunks:
        try:
            respuesta = _get_client().models.embed_content(
                model=MODELO_EMBEDDING,
                contents=chunk["texto"],
            )
            resultados.append("sin_datos")
            continue
        try:
            clasificacion = await ollama_rag.clasificar(db, documento, empresa)
            metadata = dict(documento.get("metadata_procesada") or {})
            metadata.update(ollama_rag.a_formato_legacy(clasificacion, documento))
            await repo_comprobantes.guardar_analisis(
                db,
                documento_id,
                metadata,
                EstadoProcesamiento.ANALIZADO,
            )
            resultados.append("exito")
        except Exception:
            logger.exception(
                "Error analizando con Ollama comprobante=%s", documento.get("serie_numero")
            )
            await repo_comprobantes.actualizar_estado(
                db, documento_id, EstadoProcesamiento.ERROR_ANALISIS
            )
            resultados.append("error")
    return resultado


def buscar_contexto(texto, vector_db_usuario=None, top_k=20):
    if not vector_db and not vector_db_usuario:
        return "No hay normativas contables disponibles."

    try:
        respuesta = _get_client().models.embed_content(
            model=MODELO_EMBEDDING,
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


def _normalizar_analisis(datos):
    """Devuelve el análisis como diccionario.

    `response_mime_type="application/json"` garantiza JSON válido pero no su
    forma: el modelo envuelve el objeto en una lista de vez en cuando. Guardar
    esa lista rompía después la serialización del listado de comprobantes, y
    un solo comprobante malo tumbaba la página entera.
    """
    if isinstance(datos, dict):
        return datos

    if isinstance(datos, list):
        objetos = [item for item in datos if isinstance(item, dict)]
        if len(objetos) == 1:
            return objetos[0]
        if objetos:
            # Varias respuestas para una sola factura: nos quedamos con la
            # primera, pero conviene saber que pasó.
            logger.warning(
                "El modelo devolvió %s objetos de análisis para un comprobante; "
                "se usa el primero",
                len(objetos),
            )
            return objetos[0]

    raise ValueError(
        f"El análisis devuelto no tiene la forma esperada: {type(datos).__name__}"
    )


# El prompt depende del libro. El texto original hablaba sólo de compras
# ("gasto/costo", "proveedor", `resultado: COSTO | GASTO | ACTIVO`); aplicado a
# una venta el modelo devuelve clasificaciones sin sentido, porque una factura
# emitida no es ni un costo ni un activo. Cada libro aporta su misión, sus
# reglas de serie y el enum de `resultado`; el resto del prompt es común.
_PERFIL = {
    Libro.COMPRAS: {
        "mision": "clasificar contablemente la factura",
        "contraparte": "proveedor",
        "reglas": """- Serie F (ej. F001): Factura fisica o electronica estandar. Suele
      representar compras de bienes o servicios empresariales.
    - Serie E (ej. E001): Representa facturaciones por recibos por honorarios o
      similares. Suelen ser gastos o costos directos por prestacion de
      servicios profesionales.""",
        "impacto": "como afecta este gasto/costo al rubro de la empresa auditora",
        "producto": "Nombre del item comprado o descripcion basada en la operacion",
        "razon": "Justificacion tecnica del gasto/costo",
        "cuenta": "Codigo PCGE (clase 6 para gasto o costo, clase 3 para activo)",
        "resultado": "COSTO | GASTO | ACTIVO | NO DETERMINADO",
    },
    Libro.VENTAS: {
        "mision": "clasificar contablemente el comprobante de venta emitido",
        "contraparte": "cliente",
        "reglas": """- Series F y E (ej. F001, E001): Facturas emitidas a empresas o
      profesionales; el cliente esta identificado con RUC y la operacion suele
      ser de mayor importe.
    - Series B y EB (ej. B001, EB01): Boletas de venta a consumidor final.
      Pueden venir sin documento de identidad o agrupadas como resumen diario,
      y son el grueso del registro de ventas.
    - Las notas de credito y debito modifican una venta anterior: su efecto
      sobre el ingreso es correctivo, no una venta nueva.""",
        "impacto": "a que linea de ingreso del rubro de la empresa corresponde esta venta",
        "producto": "Nombre del bien o servicio vendido, o descripcion de la operacion",
        "razon": "Justificacion tecnica del ingreso",
        "cuenta": "Codigo PCGE de la clase 70 (ventas) que corresponda",
        "resultado": "INGRESO | NO DETERMINADO",
    },
}


def extraer_datos_factura(
    texto_factura: str,
    libro: Libro = Libro.COMPRAS,
    vector_db_usuario=None,
    rubro: str = "General",
):
    contexto = buscar_contexto(texto_factura, vector_db_usuario=vector_db_usuario)
    perfil = _PERFIL[libro]

    instruccion_referencias = ""
    if vector_db_usuario:
        instruccion_referencias = """
    REGLA ADICIONAL:
    Tambien cuentas con documentos PDF subidos por el usuario.
    Si aportan contexto util, usalos para reforzar la clasificacion y mencionarlo en observaciones.
    """

    prompt = f"""
    Eres un analista contable experto especializado en el rubro: {rubro}.
    Tu mision es {perfil["mision"]} basandote en TODOS los datos en crudo (JSON) proporcionados.

    REGLAS SOBRE LA SERIE DEL COMPROBANTE:
    {perfil["reglas"]}

    ESTRATEGIA DE ANALISIS:
    - Analiza minuciosamente TODOS los campos disponibles en la informacion cruda (RAW_DATA).
    - No te limites al nombre del {perfil["contraparte"]}. Considera los montos, impuestos, tipo de operacion, moneda y cualquier otro dato relevante en el JSON.
    - Contextualiza tu decision basandote estrictamente en {perfil["impacto"]} ({rubro}).
    - NUNCA uses frases como "Clasificacion inferida por el nombre del {perfil["contraparte"]}" o "Asumiendo por...". Brinda una justificacion tecnica real basada en la combinacion de los datos proporcionados.

    {instruccion_referencias}

    CONTEXTO NORMATIVO (PCGE):
    {contexto}

    FORMATO DE SALIDA (JSON ESTRICTO):
    {{
      "detalle": [
        {{
          "producto": "{perfil["producto"]}",
          "categoria_contable": "Nombre de la categoria contable sugerida",
          "cantidad": "Cantidad (si esta disponible, si no '1')",
          "importe": "Monto de la operacion",
          "razon": "{perfil["razon"]}"
        }}
      ],
      "cuenta_contable": "{perfil["cuenta"]}",
      "centro_costos": "Centro de costos sugerido",
      "condicion_igv": "Gravado | Exonerado | Inafecto",
      "resultado": "{perfil["resultado"]}",
      "confianza": "95% | 70% | 40%",
      "estado": "Analizado | Requiere revision humana",
      "documentos": true,
      "descripcion": "Resumen tecnico de la transaccion, maximo 80 palabras",
      "observaciones": "Observaciones tecnicas reales (Evita la palabra 'inferido' y justifica usando el rubro y los datos crudos)"
    }}

    INFORMACION DEL COMPROBANTE:
    """

    response_json = _get_client().models.generate_content(
        model=MODELO_TEXTO,
        contents=[prompt, texto_factura],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )

    return _normalizar_analisis(json.loads(response_json.text))


def _build_result(total_encontradas: int, resultados: list[str]):
    return {
        "total_encontradas": len(pendientes),
        "procesadas": resultados.count("exito"),
        "errores": resultados.count("error"),
        "sin_datos": resultados.count("sin_datos"),
        "resultados": resultados,
    }


async def procesar_lote(
    db,
    empresa_id: str,
    periodo: str,
    libro: Libro = Libro.COMPRAS,
    vector_db_usuario=None,
    rubro: str = "General",
) -> dict:
    from app.repositories import comprobantes as repo_comprobantes
    from app.services.comprobante_service import texto_para_ia

    pendientes = await repo_comprobantes.listar_pendientes_analisis(
        db, empresa_id, periodo, libro
    )

    if not pendientes:
        logger.info(
            "Análisis IA sin pendientes empresa_id=%s periodo=%s libro=%s",
            empresa_id,
            periodo,
            libro.value,
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

        for intento in range(GEMINI_MAX_REINTENTOS + 1):
            await _esperar_turno_gemini()
            try:
                # Por nombre a proposito: la firma creció con `libro` y
                # pasarlos por posición metía el vector RAG en otro parámetro.
                datos = await asyncio.to_thread(
                    extraer_datos_factura,
                    texto_para_ia(documento),
                    libro=libro,
                    vector_db_usuario=vector_db_usuario,
                    rubro=rubro,
                )
                await repo_comprobantes.guardar_analisis(
                    db, documento_id, datos, EstadoProcesamiento.ANALIZADO
                )
                return "exito"
            except APIError as exc:
                if exc.code not in (429, 503) or intento == GEMINI_MAX_REINTENTOS:
                    logger.exception(
                        "Error analizando comprobante con Gemini serie_numero=%s",
                        serie_numero,
                    )
                    await repo_comprobantes.actualizar_estado(
                        db, documento_id, EstadoProcesamiento.ERROR_ANALISIS
                    )
                    return "error"

                espera = _extraer_retry_delay(exc) or GEMINI_MIN_INTERVAL_SECONDS * (
                    2**intento
                )
                logger.warning(
                    "Gemini %s (serie_numero=%s), reintentando en %.0fs (%s/%s)",
                    exc.code,
                    serie_numero,
                    espera,
                    intento + 1,
                    GEMINI_MAX_REINTENTOS,
                )
                await asyncio.sleep(espera)
            except Exception:
                logger.exception(
                    "Error analizando comprobante con Gemini serie_numero=%s", serie_numero
                )
                await repo_comprobantes.actualizar_estado(
                    db, documento_id, EstadoProcesamiento.ERROR_ANALISIS
                )
                return "error"

        return "error"

    logger.info(
        "Iniciando análisis IA empresa_id=%s periodo=%s libro=%s comprobantes=%s",
        empresa_id,
        periodo,
        libro.value,
        len(pendientes),
    )

    resultados = await asyncio.gather(*[analizar(documento) for documento in pendientes])
    resumen = _build_result(len(pendientes), list(resultados))

    logger.info(
        "Análisis IA finalizado empresa_id=%s periodo=%s libro=%s "
        "total=%s procesadas=%s errores=%s sin_datos=%s",
        empresa_id,
        periodo,
        libro.value,
        len(pendientes),
        resumen["procesadas"],
        resumen["errores"],
        resumen["sin_datos"],
    )
    return resumen
