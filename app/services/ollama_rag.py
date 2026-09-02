from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal

import numpy as np
from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings
from app.domain.catalogos import describe_comprobante
from app.repositories._mongo import (
    NOMBRE_COL_RAG_ACCOUNTS,
    NOMBRE_COL_RAG_AUDIT,
    NOMBRE_COL_RAG_COMPANY,
    NOMBRE_COL_RAG_HISTORICAL,
    NOMBRE_COL_RAG_RULES,
    NOMBRE_COL_RAG_TAX,
    monto_a_float,
)


class Evidencia(BaseModel):
    source_type: str
    source: str
    sheet: str = ""
    id: str = ""
    score: float = 0


class LineaClasificada(BaseModel):
    descripcion: str
    clasificacion: Literal["COSTO", "GASTO", "ACTIVO", "NO_APLICA"]
    cuenta: str | None = None


class Naturaleza(BaseModel):
    registro: Literal["COMPRA", "VENTA", "OTRO"]
    clasificacion: Literal["COSTO", "GASTO", "ACTIVO", "MIXTO", "NO_APLICA"]
    subtipo_operacion: str
    condicion_pago: Literal["CONTADO", "CREDITO", "NO_APLICA", "DESCONOCIDO"]
    origen_bien: Literal["COMPRA", "DONACION", "APORTE_CAPITAL", "OTRO", "NO_APLICA"]
    relacion_giro: Literal["GIRO", "NO_GIRO", "INDETERMINADO"]
    detalle_lineas: list[LineaClasificada] = Field(default_factory=list)
    estado_tributario: Literal["APTO", "NO_APTO", "CONDICIONAL", "NO_EVALUADO"]
    motivo_tributario: str = ""
    datos_faltantes: list[str] = Field(default_factory=list)
    explicacion: str

    @model_validator(mode="after")
    def mixto_con_lineas(self):
        if self.clasificacion == "MIXTO" and not self.detalle_lineas:
            raise ValueError("MIXTO requiere detalle_lineas")
        return self


class SeleccionCuenta(BaseModel):
    cuenta_base: str | None = None
    cuenta_contrapartida: str | None = None
    explicacion: str


_chat: ChatOllama | None = None
_embeddings: OllamaEmbeddings | None = None


def chat() -> ChatOllama:
    global _chat
    if _chat is None:
        _chat = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_CHAT_MODEL,
            temperature=0,
            format="json",
        )
    return _chat


def embeddings() -> OllamaEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_EMBED_MODEL
        )
    return _embeddings


def embed_documents(textos: list[str]) -> list[list[float]]:
    return embeddings().embed_documents(textos)


def embed_query(texto: str) -> list[float]:
    return embeddings().embed_query(texto)


def _tokens(texto: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúñ0-9]{3,}", texto.lower()))


async def recuperar(db, coleccion: str, consulta: str, k: int, filtro=None) -> list[dict]:
    docs = await db[coleccion].find(filtro or {}, {"_id": 0}).to_list(length=None)
    if not docs:
        return []
    vector = np.asarray(await asyncio.to_thread(embed_query, consulta))
    consulta_tokens = _tokens(consulta)
    resultados = []
    for doc in docs:
        emb = np.asarray(doc.get("embedding") or [])
        vector_score = 0.0
        if emb.size == vector.size and emb.size:
            divisor = np.linalg.norm(vector) * np.linalg.norm(emb)
            vector_score = float(np.dot(vector, emb) / divisor) if divisor else 0.0
        texto_tokens = _tokens(doc.get("texto", ""))
        lexical = len(consulta_tokens & texto_tokens) / max(len(consulta_tokens), 1)
        metadata = doc.get("metadata") or {}
        exacto = 0.0
        for valor in metadata.values():
            if str(valor).lower() in consulta.lower() and str(valor).strip():
                exacto = max(exacto, 0.15)
        resultados.append((0.65 * vector_score + 0.25 * lexical + exacto, doc))
    resultados.sort(key=lambda item: item[0], reverse=True)
    salida = []
    for score, doc in resultados[:k]:
        doc["score"] = round(score, 4)
        salida.append(doc)
    return salida


def normalizar_comprobante(documento: dict, empresa: dict) -> dict:
    detalle = documento.get("detalle_sunat") or []
    return {
        "empresa": empresa.get("razon_social") or empresa.get("ruc") or "",
        "empresa_ruc": empresa.get("ruc") or "",
        "registro": "VENTA" if documento.get("libro") == "ventas" else "COMPRA",
        "tipo_comprobante_codigo": documento.get("tipo_cp") or "",
        "tipo_comprobante": describe_comprobante(documento.get("tipo_cp") or ""),
        "serie": documento.get("serie") or "",
        "numero": documento.get("numero") or "",
        "fecha": str(documento.get("fecha_emision") or ""),
        "emisor_receptor_ruc": documento.get("documento_contraparte") or "",
        "razon_social": documento.get("razon_social") or "",
        "moneda": documento.get("moneda") or "PEN",
        "subtotal": monto_a_float(documento.get("base_imponible")),
        "igv": monto_a_float(documento.get("igv")),
        "total": monto_a_float(documento.get("total")),
        "condicion_pago_texto": (documento.get("extra") or {}).get("condicion_pago", ""),
        "fecha_vencimiento": str(documento.get("fecha_vencimiento") or ""),
        "cuotas": (documento.get("extra") or {}).get("cuotas", []),
        "items": detalle,
        "texto_adicional": (documento.get("extra") or {}).get("raw_sire", ""),
    }


def _contexto(docs: list[dict]) -> str:
    return "\n".join(f"[{d.get('score', 0):.3f}] {d.get('texto', '')}" for d in docs)


def aplicar_reglas_deterministicas(naturaleza: Naturaleza, entrada: dict) -> Naturaleza:
    """Corrige reglas objetivas que no deben quedar a criterio del LLM."""
    texto = json.dumps(entrada, ensure_ascii=False).lower()
    if not (
        entrada.get("condicion_pago_texto")
        or entrada.get("fecha_vencimiento")
        or entrada.get("cuotas")
    ):
        naturaleza.condicion_pago = "DESCONOCIDO"
    if entrada.get("registro") == "COMPRA" and any(
        señal in texto
        for señal in ("para reventa", "mercadería para reventa", "mercaderia para reventa")
    ):
        naturaleza.clasificacion = "COSTO"
        naturaleza.relacion_giro = "GIRO"
        naturaleza.subtipo_operacion = "COMPRA_GIRO"
    señales_activo = (
        "activo fijo",
        "maquinaria",
        "vehículo",
        "vehiculo",
        "laptop",
        "computadora",
        "equipo",
        "mueble",
        "inmueble",
        "capitalizable",
    )
    if naturaleza.registro == "COMPRA" and naturaleza.clasificacion == "ACTIVO":
        if not any(señal in texto for señal in señales_activo):
            naturaleza.clasificacion = "GASTO"
            naturaleza.subtipo_operacion = "GASTO_OPERATIVO"
            naturaleza.datos_faltantes.append("evidencia de activo capitalizable")
    if "donación" in texto or "donacion" in texto:
        naturaleza.origen_bien = "DONACION"
    if "aporte" in texto and ("socio" in texto or "capital" in texto):
        naturaleza.origen_bien = "APORTE_CAPITAL"
    if entrada.get("tipo_comprobante_codigo") == "09" and not any(
        señal in texto for señal in ("factura", "boleta", "recibo")
    ):
        naturaleza.clasificacion = "NO_APLICA"
        naturaleza.subtipo_operacion = "GUIA_SIN_COMPROBANTE"
    return naturaleza


async def clasificar_con_llm(db, documento: dict, empresa: dict) -> dict:
    entrada = normalizar_comprobante(documento, empresa)
    consulta = json.dumps(entrada, ensure_ascii=False, default=str)
    nombre_empresa = str(entrada["empresa"])
    reglas, historicos, empresa_docs, tributarios = await asyncio.gather(
        recuperar(db, NOMBRE_COL_RAG_RULES, consulta, settings.RAG_TOP_K_RULES),
        recuperar(
            db,
            NOMBRE_COL_RAG_HISTORICAL,
            consulta,
            settings.RAG_TOP_K_HISTORICAL,
            {"metadata.empresa": nombre_empresa},
        ),
        recuperar(
            db,
            NOMBRE_COL_RAG_COMPANY,
            consulta,
            4,
            {"metadata.empresa": nombre_empresa},
        ),
        recuperar(db, NOMBRE_COL_RAG_TAX, consulta, 4),
    )
    prompt_naturaleza = f"""Clasifica este comprobante contablemente. Separa naturaleza,
condición de pago y aptitud tributaria. No deduzcas crédito solo por cuentas 1212/4212.
Sin evidencia de pago usa DESCONOCIDO. NO_APLICA no significa falta de datos.
Una factura de compra es un DOCUMENTO, no un activo. ACTIVO solo corresponde al bien o
servicio adquirido cuando existe beneficio futuro y evidencia de capitalización. Nunca
clasifiques por la naturaleza de la cuenta por cobrar o pagar. Para compras decide COSTO,
GASTO o ACTIVO por los ítems y el giro de la empresa.
Perfil/overrides:\n{_contexto(empresa_docs)}
Reglas y ejemplos:\n{_contexto(reglas)}\nHistóricos de la misma empresa:\n{_contexto(historicos)}
Normativa documental:\n{_contexto(tributarios)}\nCOMPROBANTE:\n{consulta}"""
    naturaleza = await asyncio.to_thread(
        chat().with_structured_output(Naturaleza).invoke, prompt_naturaleza
    )
    naturaleza = aplicar_reglas_deterministicas(naturaleza, entrada)

    query_cuenta = f"{consulta}\n{naturaleza.model_dump_json()}"
    candidatas = await recuperar(
        db, NOMBRE_COL_RAG_ACCOUNTS, query_cuenta, settings.RAG_TOP_K_ACCOUNTS
    )
    codigos_regla: list[str] = []
    if naturaleza.registro == "COMPRA" and naturaleza.clasificacion == "COSTO":
        codigos_regla.append("6011020")
    if naturaleza.origen_bien == "DONACION":
        codigos_regla.extend(["20111", "7593"])
    if naturaleza.origen_bien == "APORTE_CAPITAL":
        codigos_regla.extend(["20111", "5221", "5011", "5012"])
    if naturaleza.subtipo_operacion == "VENTA_ACTIVO_FIJO":
        codigos_regla.extend(["7564", "1653", "65514"])
    if codigos_regla:
        extras = (
            await db[NOMBRE_COL_RAG_ACCOUNTS]
            .find({"metadata.code": {"$in": codigos_regla}}, {"_id": 0})
            .to_list(length=None)
        )
        conocidos = {d.get("metadata", {}).get("code") for d in candidatas}
        candidatas.extend(d for d in extras if d.get("metadata", {}).get("code") not in conocidos)
    prompt_cuenta = f"""Elige y rankea exclusivamente entre estas cuentas CONTASIS.
No inventes códigos. Si ninguna aplica, devuelve null. La condición de pago es independiente.
CLASIFICACION: {naturaleza.model_dump_json()}
CANDIDATAS:\n{_contexto(candidatas)}"""
    seleccion = await asyncio.to_thread(
        chat().with_structured_output(SeleccionCuenta).invoke, prompt_cuenta
    )

    plan = {str(d.get("metadata", {}).get("code")): d for d in candidatas}
    faltantes = list(naturaleza.datos_faltantes)
    if (
        naturaleza.registro == "COMPRA"
        and naturaleza.clasificacion == "COSTO"
        and "para reventa" in consulta.lower()
        and "6011020" in plan
    ):
        seleccion.cuenta_base = "6011020"
    if seleccion.cuenta_base not in plan:
        seleccion.cuenta_base = None
        faltantes.append("cuenta_base válida")
    cuenta_base = str(seleccion.cuenta_base or "")
    prefijos_base = {
        ("COMPRA", "COSTO"): ("20", "21", "23", "24", "25", "60", "61", "69"),
        ("COMPRA", "GASTO"): ("62", "63", "64", "65", "67", "68"),
        ("COMPRA", "ACTIVO"): ("3",),
        ("VENTA", "NO_APLICA"): ("70", "75", "77"),
    }.get((naturaleza.registro, naturaleza.clasificacion))
    if cuenta_base and prefijos_base and not cuenta_base.startswith(prefijos_base):
        seleccion.cuenta_base = None
        faltantes.append("cuenta_base compatible con naturaleza y registro")
    if seleccion.cuenta_contrapartida and seleccion.cuenta_contrapartida not in plan:
        seleccion.cuenta_contrapartida = None
        faltantes.append("cuenta_contrapartida válida")
    if naturaleza.registro == "COMPRA" and str(seleccion.cuenta_contrapartida).startswith("12"):
        seleccion.cuenta_contrapartida = None
        faltantes.append("contrapartida compatible con compra")
    if naturaleza.registro == "VENTA" and str(seleccion.cuenta_contrapartida).startswith("42"):
        seleccion.cuenta_contrapartida = None
        faltantes.append("contrapartida compatible con venta")
    if (
        naturaleza.origen_bien in {"DONACION", "APORTE_CAPITAL"}
        and seleccion.cuenta_contrapartida == "4212"
    ):
        seleccion.cuenta_contrapartida = None
        faltantes.append("contrapartida no comercial")

    fuentes = reglas + empresa_docs + historicos + tributarios + candidatas
    componentes = [
        min((reglas[0].get("score", 0) if reglas else 0), 1) * 0.30,
        min((empresa_docs[0].get("score", 0) if empresa_docs else 0), 1) * 0.20,
        (0.20 if seleccion.cuenta_base else 0),
        min((historicos[0].get("score", 0) if historicos else 0), 1) * 0.15,
        (0.10 if entrada["items"] else 0.04),
        (0.05 if naturaleza.estado_tributario != "NO_EVALUADO" else 0),
    ]
    confianza = round(min(sum(componentes), 1), 2)
    requiere_revision = confianza < settings.RAG_CONFIDENCE_THRESHOLD or bool(faltantes)
    evidencias = [
        Evidencia(
            source_type=str(d.get("metadata", {}).get("source_type", "")),
            source=str(d.get("metadata", {}).get("file", "")),
            sheet=str(d.get("metadata", {}).get("sheet", "")),
            id=str(d.get("metadata", {}).get("row_id", "")),
            score=d.get("score", 0),
        ).model_dump()
        for d in fuentes[:12]
    ]
    cuenta_doc = plan.get(seleccion.cuenta_base or "", {})
    salida = {
        **naturaleza.model_dump(),
        "cuenta_base": seleccion.cuenta_base,
        "cuenta_base_desc": cuenta_doc.get("metadata", {}).get("description", ""),
        "cuenta_contrapartida": seleccion.cuenta_contrapartida,
        "cuenta_contrapartida_desc": plan.get(seleccion.cuenta_contrapartida or "", {})
        .get("metadata", {})
        .get("description", ""),
        "confianza": confianza,
        "requiere_revision": requiere_revision,
        "datos_faltantes": sorted(set(faltantes)),
        "evidencias": evidencias,
        "explicacion": f"{naturaleza.explicacion} {seleccion.explicacion}".strip(),
    }
    entrada_hash = hashlib.sha256(consulta.encode()).hexdigest()
    await db[NOMBRE_COL_RAG_AUDIT].insert_one(
        {
            "timestamp": datetime.now(UTC),
            "clave_comprobante": (
                f"{entrada['tipo_comprobante_codigo']}-{entrada['serie']}-{entrada['numero']}"
            ),
            "empresa": nombre_empresa,
            "input_hash": entrada_hash,
            "model_chat": settings.OLLAMA_CHAT_MODEL,
            "model_embedding": settings.OLLAMA_EMBED_MODEL,
            "retrieved_ids": [e["id"] for e in evidencias],
            "cuentas_candidatas": list(plan),
            "salida_rag": salida,
            "revision_manual": None,
            "correccion_final": None,
        }
    )
    return salida


def _normalizado(texto: str) -> str:
    return " ".join(re.findall(r"[A-Z0-9]+", texto.upper()))


def _naturaleza_desde_cuenta(registro: str, cuenta: str) -> tuple[str, str]:
    if registro == "VENTA":
        return "NO_APLICA", "VENTA_GIRO" if cuenta.startswith("70") else "VENTA_NO_GIRO"
    if cuenta.startswith(("20", "21", "23", "24", "25", "60", "61", "69")):
        return "COSTO", "COMPRA_GIRO"
    if cuenta.startswith("3"):
        return "ACTIVO", "COMPRA_ACTIVO"
    if cuenta.startswith(("62", "63", "64", "65", "67", "68")):
        return "GASTO", "GASTO_OPERATIVO"
    return "NO_APLICA", "OTRO"


async def clasificar(db, documento: dict, empresa: dict) -> dict:
    """Clasifica solo por recuperación RAG; no invoca ningún modelo generativo."""
    entrada = normalizar_comprobante(documento, empresa)
    consulta = _glosa(documento, {"subtipo_operacion": ""})
    registro = str(entrada["registro"])
    empresa_ruc = str(empresa.get("ruc") or "")
    alias_empresa = {"20608997106": "JOAQUISAN"}.get(empresa_ruc)
    filtro_historico: dict[str, object] = {"metadata.registro": registro}
    if alias_empresa:
        filtro_historico["metadata.empresa"] = alias_empresa

    historicos, reglas, empresa_docs = await asyncio.gather(
        recuperar(db, NOMBRE_COL_RAG_HISTORICAL, consulta, 12, filtro_historico),
        recuperar(db, NOMBRE_COL_RAG_RULES, consulta, settings.RAG_TOP_K_RULES),
        recuperar(
            db,
            NOMBRE_COL_RAG_COMPANY,
            consulta,
            4,
            {"metadata.empresa": alias_empresa},
        )
        if alias_empresa
        else asyncio.sleep(0, result=[]),
    )

    glosa_n = _normalizado(consulta)
    proveedor_ruc = str(documento.get("documento_contraparte") or "")
    pares: dict[tuple[str, str], float] = {}
    for posicion, candidato in enumerate(historicos):
        meta = candidato.get("metadata") or {}
        base = str(meta.get("code") or "")
        total = str(meta.get("cuenta_total") or "")
        if not base:
            continue
        peso = max(float(candidato.get("score") or 0), 0.01) / (1 + posicion * 0.1)
        if glosa_n and _normalizado(str(meta.get("glosa") or "")) == glosa_n:
            peso += 2.0
        if proveedor_ruc and str(meta.get("proveedor_ruc") or "") == proveedor_ruc:
            peso += 0.75
        pares[(base, total)] = pares.get((base, total), 0) + peso

    candidatas_plan = []
    if pares:
        cuenta_base, cuenta_total = max(pares.items(), key=lambda item: item[1])[0]
        mejor_peso = max(pares.values())
    else:
        candidatas_plan = await recuperar(
            db, NOMBRE_COL_RAG_ACCOUNTS, consulta, settings.RAG_TOP_K_ACCOUNTS
        )
        cuenta_base = str(
            (candidatas_plan[0].get("metadata") or {}).get("code") if candidatas_plan else ""
        )
        cuenta_total = "4212" if registro == "COMPRA" else "1212"
        mejor_peso = float(candidatas_plan[0].get("score") or 0) if candidatas_plan else 0

    existe_base = bool(
        cuenta_base and await db[NOMBRE_COL_RAG_ACCOUNTS].find_one({"metadata.code": cuenta_base})
    )
    existe_total = bool(
        cuenta_total and await db[NOMBRE_COL_RAG_ACCOUNTS].find_one({"metadata.code": cuenta_total})
    )
    if not existe_base:
        cuenta_base = ""
    if not existe_total:
        cuenta_total = ""

    clasificacion, subtipo = _naturaleza_desde_cuenta(registro, cuenta_base)
    confianza = round(min(0.45 + mejor_peso * 0.35, 0.99), 2) if cuenta_base else 0.2
    requiere_revision = not cuenta_base or confianza < settings.RAG_CONFIDENCE_THRESHOLD
    fuentes = historicos[:8] + reglas[:4] + empresa_docs[:4] + candidatas_plan[:4]
    evidencias = [
        Evidencia(
            source_type=str((d.get("metadata") or {}).get("source_type", "")),
            source=str((d.get("metadata") or {}).get("file", "")),
            sheet=str((d.get("metadata") or {}).get("sheet", "")),
            id=str((d.get("metadata") or {}).get("row_id", "")),
            score=float(d.get("score") or 0),
        ).model_dump()
        for d in fuentes
    ]
    salida = {
        "registro": registro,
        "clasificacion": clasificacion,
        "subtipo_operacion": subtipo,
        "condicion_pago": "DESCONOCIDO",
        "origen_bien": "COMPRA" if registro == "COMPRA" else "NO_APLICA",
        "relacion_giro": "GIRO" if subtipo.endswith("GIRO") else "INDETERMINADO",
        "detalle_lineas": [],
        "estado_tributario": "APTO"
        if documento.get("tipo_cp") in {"01", "02", "04"}
        else "CONDICIONAL",
        "motivo_tributario": "Evaluación documental basada en el tipo de comprobante.",
        "cuenta_base": cuenta_base or None,
        "cuenta_base_desc": "",
        "cuenta_contrapartida": cuenta_total or None,
        "cuenta_contrapartida_desc": "",
        "confianza": confianza,
        "requiere_revision": requiere_revision,
        "datos_faltantes": [] if cuenta_base else ["cuenta CONTASIS recuperable"],
        "evidencias": evidencias,
        "explicacion": (
            "Cuenta seleccionada por similitud y precedentes de "
            f"{alias_empresa or 'la base histórica'}; "
            "sin intervención de un modelo generativo."
        ),
    }
    consulta_auditoria = json.dumps(entrada, ensure_ascii=False, default=str)
    await db[NOMBRE_COL_RAG_AUDIT].insert_one(
        {
            "timestamp": datetime.now(UTC),
            "clave_comprobante": (
                f"{documento.get('tipo_cp', '')}-{documento.get('serie_numero', '')}"
            ),
            "empresa": alias_empresa or empresa_ruc,
            "input_hash": hashlib.sha256(consulta_auditoria.encode()).hexdigest(),
            "model_chat": "disabled",
            "model_embedding": settings.OLLAMA_EMBED_MODEL,
            "retrieved_ids": [e["id"] for e in evidencias],
            "cuentas_candidatas": [f"{b}|{t}" for b, t in pares],
            "salida_rag": salida,
            "revision_manual": None,
            "correccion_final": None,
        }
    )
    return salida


def _condicion_igv(documento: dict) -> str:
    if monto_a_float(documento.get("igv")) > 0:
        return "Gravado"
    if monto_a_float(documento.get("exonerado")) > 0:
        return "Exonerado"
    if (
        monto_a_float(documento.get("inafecto")) > 0
        or monto_a_float(documento.get("no_gravado")) > 0
    ):
        return "Inafecto"
    return "No determinado"


def _glosa(documento: dict, resultado: dict) -> str:
    glosa_guardada = str(
        (((documento.get("metadata_procesada") or {}).get("rag") or {}).get("glosa")) or ""
    ).strip()
    if glosa_guardada:
        return glosa_guardada[:500]
    descripciones = []
    for item in documento.get("detalle_sunat") or []:
        if not isinstance(item, dict):
            continue
        descripcion = str(item.get("descripcion") or "").strip()
        if descripcion and descripcion not in descripciones:
            descripciones.append(descripcion)
    if descripciones:
        return " / ".join(descripciones)[:500]
    return str(documento.get("razon_social") or resultado.get("subtipo_operacion") or "")[:500]


def a_formato_legacy(resultado: dict, documento: dict | None = None) -> dict:
    documento = documento or {}
    confianza = float(resultado.get("confianza") or 0)
    clasificacion = str(resultado.get("clasificacion") or "NO DETERMINADO")
    resultado_legacy = (
        clasificacion if clasificacion in {"COSTO", "GASTO", "ACTIVO"} else "NO DETERMINADO"
    )
    detalle = []
    for item in documento.get("detalle_sunat") or []:
        if not isinstance(item, dict):
            continue
        detalle.append(
            {
                "producto": item.get("descripcion") or "Ítem del comprobante",
                "categoria_contable": resultado_legacy,
                "cantidad": item.get("cantidad") or 1,
                "importe": item.get("importe") or item.get("valor_venta"),
                "razon": resultado.get("explicacion"),
            }
        )
    if not detalle:
        detalle.append(
            {
                "producto": _glosa(documento, resultado),
                "categoria_contable": resultado_legacy,
                "cantidad": 1,
                "importe": monto_a_float(documento.get("total")),
                "razon": resultado.get("explicacion"),
            }
        )
    return {
        "detalle": detalle,
        "cuenta_contable": resultado.get("cuenta_base"),
        "centro_costos": None,
        "condicion_igv": _condicion_igv(documento),
        "resultado": resultado_legacy,
        "confianza": f"{confianza:.0%}",
        "estado": "Requiere revision humana" if resultado.get("requiere_revision") else "Analizado",
        "documentos": bool(resultado.get("evidencias")),
        "descripcion": _glosa(documento, resultado)[:300],
        "observaciones": str(resultado.get("explicacion") or "")[:500],
        "rag": {
            "codigo_comprobante": documento.get("tipo_cp"),
            "codigo_identidad": documento.get("tipo_doc_identidad"),
            "cuenta_base": resultado.get("cuenta_base"),
            "cuenta_total": resultado.get("cuenta_contrapartida"),
            "glosa": _glosa(documento, resultado),
            "respuesta_cuentas": json.dumps(resultado, ensure_ascii=False),
        },
    }
