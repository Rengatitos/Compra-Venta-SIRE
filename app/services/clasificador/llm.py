from __future__ import annotations

import ast
import json
import logging
import os
import re
import threading
import time
from typing import Any

from app.services.clasificador.config import Settings
from app.services.clasificador.schemas import (
    ClassificationCore,
    EconomicPurpose,
    OperationInterpretation,
)

logger = logging.getLogger(__name__)


class GeminiGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self._loaded = False
        self._generation_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._loaded

    @staticmethod
    def _gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
        """Removes Pydantic's permissive-object keyword unsupported by Gemini schemas."""
        cleaned = json.loads(json.dumps(schema))

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                node.pop("additionalProperties", None)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(cleaned)
        return cleaned

    def load(self) -> None:
        if self._loaded:
            return
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Falta google-genai. Instale requirements.txt") from exc
        credentials = self.settings.google_application_credentials
        if credentials:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", credentials)
        if not credentials or not os.path.exists(credentials):
            logger.warning("GOOGLE_APPLICATION_CREDENTIALS no está configurada o no existe; Vertex AI quedará deshabilitado")
            return
        self.client = genai.Client(
            vertexai=True,
            project=self.settings.vertex_project,
            location=self.settings.vertex_location,
        )
        self._loaded = True
        logger.info("Cliente Gemini listo: %s", self.settings.gemini_model)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
        web_search: bool = False,
    ) -> tuple[dict[str, Any], str]:
        """Pide a Gemini un objeto JSON.

        Con `web_search` Gemini puede consultar Google Search (grounding). En
        Vertex AI la búsqueda y la salida estructurada (`response_schema`) no
        conviven: con el esquema el modelo contesta sin buscar. Por eso, al
        buscar, el esquema va en las instrucciones y la respuesta se valida
        igual después con Pydantic.
        """
        web_search = web_search and self.settings.gemini_web_search
        if not self._loaded:
            self.load()
        if self.client is None:
            raise RuntimeError("GEMINI_API_ERROR: credencial de Vertex AI no está configurada")
        with self._generation_lock:
            from google.genai import types

            config_kwargs: dict[str, Any] = {
                "system_instruction": system_prompt,
                "temperature": 0,
                "max_output_tokens": self.settings.max_new_tokens,
            }
            if web_search:
                config_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
                if response_schema:
                    config_kwargs["system_instruction"] = (
                        f"{system_prompt}\nPuedes buscar en internet para identificar qué vende o hace "
                        "la contraparte. Devuelve SOLO un objeto JSON que cumpla este JSON Schema, sin "
                        f"Markdown: {json.dumps(self._gemini_schema(response_schema), ensure_ascii=False)}"
                    )
            else:
                config_kwargs["response_mime_type"] = "application/json"
                if response_schema:
                    config_kwargs["response_schema"] = self._gemini_schema(response_schema)
            response = None
            last_error: Exception | None = None
            for attempt in range(self.settings.gemini_max_retries + 1):
                try:
                    response = self.client.models.generate_content(
                        model=self.settings.gemini_model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(**config_kwargs),
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    message = str(exc).lower()
                    transient = any(term in message for term in ("429", "500", "502", "503", "504", "timeout", "temporarily"))
                    if not transient or attempt >= self.settings.gemini_max_retries:
                        raise RuntimeError(f"GEMINI_API_ERROR: {exc}") from exc
                    time.sleep(0.5 * (2 ** attempt))
            if response is None:
                raise RuntimeError(f"GEMINI_API_ERROR: {last_error}")
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = getattr(candidates[0], "finish_reason", None)
                finish_name = getattr(finish_reason, "name", str(finish_reason).split(".")[-1])
                if finish_reason and finish_name not in {"STOP", "0"}:
                    raise RuntimeError(f"Gemini no generó una respuesta válida: {finish_reason}")
            try:
                text = (getattr(response, "text", None) or "").strip()
            except Exception as exc:
                raise RuntimeError("Gemini no devolvió una parte de texto válida") from exc
            if not text:
                raise RuntimeError("Gemini devolvió una respuesta vacía")
            data = self._parse_json(text)
            return data, text

    def interpret_operation(self, payload: dict[str, Any], context_hits: list[dict[str, Any]]) -> OperationInterpretation:
        system = (
            "Interpreta economicamente un comprobante peruano usando solo los hechos y evidencia entregados. "
            "No selecciones cuentas contables. Prioriza descripcion/items, luego actividad compatible de contraparte, "
            "empresa y contexto CIIU. Una actividad secundaria puede ser mas relevante que la principal. "
            "Identifica primero QUE es cada item: si es un codigo, nombre comercial o sigla (p. ej. 'DIESEL B5 S50'), "
            "averigua que producto o servicio es. Luego decide si guarda relacion con la actividad principal de la "
            "empresa (la marcada como elegida por la empresa manda sobre la de SUNAT): si no la guarda, marca "
            "operacion_fuera_giro_probable=true y explicalo en razon."
        )
        data, _ = self.generate_json(
            system,
            json.dumps({"operacion": payload, "contexto_ciiu_recuperado": context_hits}, ensure_ascii=False),
            OperationInterpretation.model_json_schema(),
            web_search=True,
        )
        return OperationInterpretation.model_validate(data)

    def interpret_economic_purpose(self, payload: dict[str, Any], interpretation: dict[str, Any], context_hits: list[dict[str, Any]]) -> EconomicPurpose:
        system = (
            "Determina para qué función de la EMPRESA se utiliza la compra o qué operación representa la venta. "
            "Compara items, descripción, actividad de la empresa y actividad relevante de la contraparte con evidencia CIIU. "
            "La actividad de la empresa no define directamente la cuenta. No selecciones códigos contables. "
            "Distingue administración, ventas, producción, operación, mercadería, activo y costo directo. "
            "Si faltan datos para distinguir reventa, cortesía, consumo interno o área de un viaje, responde INDETERMINADO y reduce confianza. "
            "CDS solo si el contexto explica su significado. No inventes finalidad. Devuelve JSON."
        )
        data, _ = self.generate_json(system, json.dumps({"comprobante": payload, "interpretacion": interpretation, "evidencia": context_hits}, ensure_ascii=False), EconomicPurpose.model_json_schema(), web_search=True)
        return EconomicPurpose.model_validate(data)

    def classify_with_candidates(
        self,
        payload: dict[str, Any],
        interpretation: dict[str, Any],
        base_candidates: list[dict[str, Any]],
        total_candidates: list[dict[str, Any]],
        context_hits: list[dict[str, Any]],
    ) -> ClassificationCore:
        system = (
            "Clasifica un comprobante peruano usando exclusivamente la interpretacion, candidatos y evidencia. "
            "Elige cuentas solo de las listas recibidas; si ninguna es suficiente devuelve null. "
            "Usa finalidad económica para escoger hoja funcional; si es INDETERMINADO y hay hojas por área, devuelve null. "
            "No inventes codigos ni fuerces 1212/4212. Devuelve solo JSON."
        )
        data, _ = self.generate_json(
            system,
            json.dumps({
                "operacion": payload,
                "interpretacion": interpretation,
                "candidatos_base": base_candidates,
                "candidatos_total": total_candidates,
                "evidencia_contextual": context_hits,
            }, ensure_ascii=False),
            ClassificationCore.model_json_schema(),
        )
        return ClassificationCore.model_validate(data)

    @staticmethod
    def _extract_braced(text: str) -> str:
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE | re.DOTALL)
        start = text.find("{")
        if start < 0:
            return text
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return text[start:]

    @classmethod
    def _parse_json(cls, text: str) -> dict[str, Any]:
        candidate = cls._extract_braced(text)
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        try:
            data = ast.literal_eval(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        raise ValueError(f"Gemini no devolvió JSON válido. Salida: {text[:1000]}")
