from __future__ import annotations

import json
import math
import re
from typing import Any

from app.services.clasificador.config import Settings
from app.services.clasificador.schemas import (
    AccountCandidate,
    ClassificationCore,
    ClassificationResponse,
    ClassifyRequest,
    ConfidenceComponents,
    EconomicActivity,
    EconomicPurpose,
    OperationInterpretation,
)
from app.services.clasificador.text import normalize_for_search, tokenize

SYSTEM_PROMPT = """Eres un clasificador contable basado en evidencia recuperada por RAG.
Tu tarea es clasificar UN comprobante de compra o venta.

REGLAS OBLIGATORIAS:
- Usa únicamente los DATOS DEL COMPROBANTE y el CONTEXTO RAG entregado.
- No inventes códigos de cuentas. Una cuenta contable debe estar respaldada por el contexto RAG.
- Si el contexto no permite determinar una cuenta, usa null en esa cuenta y explícalo en razon.
- Distingue compra/venta, bienes/servicios y contexto económico usando la evidencia recuperada.
- La actividad económica de empresa/proveedor es contexto, no una orden que invalide la descripción real del comprobante.
- La confianza final NO puede superar LIMITE_CONFIANZA_RAG.
- Devuelve exclusivamente un objeto JSON, sin Markdown ni texto adicional.

ESQUEMA EXACTO:
{
  "clasificacion": "string",
  "subtipo": "string",
  "cuenta_base_imponible": {"codigo":"string","descripcion":"string"} | null,
  "cuenta_total": {"codigo":"string","descripcion":"string"} | null,
  "centro_costos": "string" | null,
  "condicion_igv": "string",
  "confianza": 0.0,
  "razon": "explicación breve y fundamentada"
}
"""


class ClassifierService:
    def __init__(self, settings: Settings, rag, llm, company_heads=None):
        self.settings = settings
        self.rag = rag
        self.llm = llm
        self.company_heads = company_heads

    def _resolve_request(self, payload: ClassifyRequest) -> ClassifyRequest:
        company = payload.empresa
        if company is None and payload.empresa_ruc and self.company_heads:
            company = self.company_heads.get(payload.empresa_ruc)
        if company is None:
            raise ValueError("COMPANY_CONTEXT_NOT_FOUND: registre empresa o empresa_ruc")

        voucher = payload.comprobante
        counterparty = voucher.contraparte
        if counterparty is None and payload.contraparte_ruc and self.company_heads:
            head = self.company_heads.get(payload.contraparte_ruc)
            if head:
                counterparty = head.model_copy(update={"tipo_documento": "6", "numero_documento": head.ruc})
        if counterparty is not voucher.contraparte:
            voucher = voucher.model_copy(update={"contraparte": counterparty})
        return payload.model_copy(update={"empresa": company, "comprobante": voucher})

    @staticmethod
    def _facts(payload: ClassifyRequest) -> dict[str, Any]:
        company = payload.empresa
        cp = payload.comprobante.contraparte
        return {
            "company_ruc": company.ruc if company else None,
            "provider_ruc": cp.numero_documento if cp else None,
            "company_ciiu": [a.ciiu_v4 or a.ciiu for a in (company.actividades_economicas if company else []) if a.ciiu_v4 or a.ciiu],
            "counterparty_ciiu": [a.ciiu_v4 or a.ciiu for a in (cp.actividades_economicas if cp else []) if a.ciiu_v4 or a.ciiu],
            "tipo_cp": payload.comprobante.tipo_cp.codigo,
            "libro": payload.comprobante.libro,
        }

    @staticmethod
    def _items_text(payload: ClassifyRequest) -> str:
        return "\n".join(
            f"{item.descripcion}; codigo={item.codigo or ''}; cantidad={item.cantidad or ''}; unidad={item.unidad_medida or ''}"
            for item in payload.items
        )

    @staticmethod
    def _activities_text(activities: list[EconomicActivity]) -> str:
        return "\n".join(f"{a.tipo or ''} CIIU {a.ciiu_v4 or a.ciiu or ''}: {a.descripcion or ''}" for a in activities)

    def build_context_query(self, payload: ClassifyRequest) -> str:
        company = payload.empresa
        cp = payload.comprobante.contraparte
        return "\n".join([
            f"Empresa {company.ruc if company else ''}: {company.razon_social if company else ''}",
            self._activities_text(company.actividades_economicas if company else []),
            f"Contraparte {cp.numero_documento if cp else ''}: {cp.razon_social if cp else ''}",
            self._activities_text(cp.actividades_economicas if cp else []),
            f"Libro: {payload.comprobante.libro}; comprobante: {payload.comprobante.tipo_cp.codigo} {payload.comprobante.tipo_cp.descripcion or ''}",
            f"Items:\n{self._items_text(payload)}",
        ])

    @staticmethod
    def _amount_condition(payload: ClassifyRequest) -> str:
        amounts = payload.comprobante.importes
        if not amounts:
            return "NO_DETERMINADA"
        if (amounts.exonerado or 0) > 0:
            return "EXONERADO"
        if (amounts.inafecto or 0) > 0:
            return "INAFECTO"
        if (amounts.no_gravado or 0) > 0:
            return "NO_GRAVADO"
        if (amounts.igv or 0) > 0 or (amounts.base_imponible or 0) > 0:
            return "GRAVADO"
        return "NO_DETERMINADA"

    @staticmethod
    def _hit_dicts(rag, hits: list[Any]) -> list[dict[str, Any]]:
        return [e.model_dump(mode="json") for e in rag.evidence(hits)]

    @staticmethod
    def _area_in_description(description: str) -> str | None:
        segments = {normalize_for_search(part).strip(" .:") for part in re.split(r"\s+-\s+", description.split(";")[0])}
        labels = {
            "ADMINISTRACION": {"adm", "admin", "administracion", "administrativo", "administrativa"},
            "VENTAS": {"vtas", "ventas"},
            "PRODUCCION": {"prod", "produccion"},
            "CDS": {"cds"},
        }
        matches = [area for area, aliases in labels.items() if segments & aliases]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _candidate_from_hit(hit: Any, facts: dict[str, Any], purpose: str) -> AccountCandidate | None:
        metadata = hit.chunk.metadata or {}
        code = str(metadata.get("cuenta") or metadata.get("codigo") or "").strip()
        if not code:
            match = re.search(r"(?:cuenta|codigo|col_[34])\s*[:#]?\s*([0-9][0-9.\-]*)", hit.chunk.content, re.IGNORECASE)
            code = match.group(1) if match else ""
        if not code:
            return None
        description = str(metadata.get("descripcion") or (re.search(r"DESCRIPCION:\s*([^\n]+)", hit.chunk.content, re.IGNORECASE) or [None, hit.chunk.content[:500]])[1])
        operation_tokens = set(tokenize(str(facts.get("operation_text") or "")))
        content_tokens = set(tokenize(hit.chunk.content))
        description_tokens = set(tokenize(description))
        leaf_bonus = 1.0 if metadata.get("es_cuenta_hoja") in {True, "true", "Sí", "SI", "si"} or metadata.get("centro_costos") or "col_4:" in hit.chunk.content[:40].lower() else 0.0
        meaningful = {token for token in operation_tokens if len(token) > 3 and token not in {"servicio", "compra", "venta"}}
        concept_match = len(meaningful & content_tokens) / len(meaningful) if meaningful else float(hit.semantic_score)
        description_match = len(meaningful & description_tokens) / len(meaningful) if meaningful else float(hit.lexical_score)
        area = str(facts.get("area_funcional") or "INDETERMINADO")
        leaf_area = ClassifierService._area_in_description(description)
        functional = 1.0 if leaf_area == area else (0.0 if leaf_area else 0.5)
        components = {
            "semantic_concept": max(concept_match, float(hit.semantic_score) * 0.7),
            "account_description": max(description_match, float(hit.lexical_score) * 0.5),
            "functional_area": functional,
            "operation_nature": 1.0 if any(t in content_tokens for t in set(tokenize(str(facts.get("operation_nature") or "")))) else 0.5,
            "supplier_activity": float(hit.metadata_score) if facts.get("counterparty_ciiu") else 0.5,
            "company_context": float(hit.metadata_score) if facts.get("company_ciiu") else 0.5,
            "leaf_specificity": leaf_bonus,
        }
        if purpose == "total_account":
            weights = {"semantic_concept": .30, "account_description": .25, "functional_area": 0.0, "operation_nature": .15, "supplier_activity": .10, "company_context": .10, "leaf_specificity": .10}
        else:
            weights = {"semantic_concept": .25, "account_description": .20, "functional_area": .25, "operation_nature": .10, "supplier_activity": .08, "company_context": .07, "leaf_specificity": .05}
        final_score = sum(components[name] * weight for name, weight in weights.items())
        if purpose == "total_account" and len(code) >= 4 and leaf_bonus:
            final_score += 0.08
        return AccountCandidate(codigo=code, descripcion=description, score=final_score, source=hit.chunk.source, metadata=metadata, score_components=components)

    def _account_candidates(self, hits: list[Any], facts: dict[str, Any], purpose: str) -> list[AccountCandidate]:
        candidates: list[AccountCandidate] = []
        seen: set[str] = set()
        for hit in hits:
            candidate = self._candidate_from_hit(hit, facts, purpose)
            if candidate and candidate.codigo not in seen:
                candidates.append(candidate)
                seen.add(candidate.codigo)
        return candidates

    @staticmethod
    def build_base_account_query(interpretation: OperationInterpretation, purpose: EconomicPurpose) -> str:
        return "\n".join(filter(None, [interpretation.direccion, interpretation.naturaleza, interpretation.concepto, purpose.area_funcional, purpose.tratamiento_contable]))

    @staticmethod
    def build_total_account_query(payload: ClassifyRequest, direction: str) -> str:
        voucher = payload.comprobante
        if direction.upper() == "VENTA":
            role = "CUENTAS POR COBRAR COMERCIALES TERCEROS factura emitida en cartera 12 121 1212"
        else:
            role = "CUENTAS POR PAGAR COMERCIALES TERCEROS factura recibida emitida 42 421 4212"
        return "\n".join([direction, voucher.tipo_cp.codigo, voucher.tipo_cp.descripcion or "", role])

    @staticmethod
    def _base_compatible(candidate: AccountCandidate, interpretation: OperationInterpretation, purpose: EconomicPurpose) -> bool:
        code = candidate.codigo
        text = normalize_for_search(candidate.descripcion or "")
        direction = interpretation.direccion.upper()
        nature = interpretation.naturaleza.upper()
        if direction == "VENTA":
            treatment = (purpose.tratamiento_contable or "").upper()
            if "BIEN" in nature and purpose.area_funcional == "INDETERMINADO":
                return False
            if any(term in nature for term in ("INMUEBLE", "TERRENO")) and (purpose.area_funcional == "INDETERMINADO" or not treatment or "INDETERMINADO" in treatment):
                return False
            return code.startswith("70") and ("SERVICIO" not in nature or code.startswith("703"))
        if direction == "COMPRA":
            if purpose.area_funcional == "MERCADERIA" or "MERCADER" in (purpose.tratamiento_contable or "").upper():
                return code.startswith("60") and "servicio" not in text
            if "BIEN" in nature:
                return not code.startswith("63")
            if "SERVICIO" in nature:
                return not code.startswith("60")
        return True

    @staticmethod
    def _total_compatible(candidate: AccountCandidate, direction: str) -> bool:
        if direction.upper() == "VENTA":
            return candidate.codigo.startswith("12") and "por pagar" not in normalize_for_search(candidate.descripcion or "")
        if direction.upper() == "COMPRA":
            return candidate.codigo.startswith("42") and "por cobrar" not in normalize_for_search(candidate.descripcion or "")
        return False

    @staticmethod
    def _apply_document_fit(candidates: list[AccountCandidate], payload: ClassifyRequest, interpretation: OperationInterpretation, purpose: EconomicPurpose, stage: str) -> list[AccountCandidate]:
        fitted = []
        company_ruc = payload.empresa.ruc if payload.empresa else None
        counterparty = payload.comprobante.contraparte
        third_party = bool(company_ruc and counterparty and counterparty.numero_documento and company_ruc != counterparty.numero_documento)
        issued = payload.comprobante.tipo_cp.codigo in {"01", "03"}
        local = "LOCAL" in (interpretation.tipo_operacion or "").upper() or "LOCAL" in (payload.comprobante.origen or "").upper()
        for candidate in candidates:
            description = normalize_for_search(candidate.descripcion or "")
            adjustment = 0.0
            if stage == "total_account":
                if issued and "emitidas" in description and "no emitidas" not in description:
                    adjustment += 0.22
                if issued and "no emitidas" in description:
                    adjustment -= 0.20
                if "cobranza" in description or "descuento" in description:
                    adjustment -= 0.10
                if len(candidate.codigo) <= 3:
                    adjustment -= 0.12
            else:
                if "col_3" in str(candidate.metadata).lower() or (len(candidate.codigo) <= 4 and not candidate.metadata.get("centro_costos")):
                    adjustment -= 0.15
                if purpose.area_funcional == "MERCADERIA":
                    if candidate.codigo.startswith("601"):
                        adjustment += 0.25
                    elif candidate.codigo.startswith("609"):
                        adjustment -= 0.20
                if interpretation.direccion.upper() == "VENTA" and local:
                    adjustment += 0.15 if "venta local" in description else -0.12
                if third_party and "terceros" in description:
                    adjustment += 0.10
                if third_party and "relacionadas" in description:
                    adjustment -= 0.15
            fitted.append(candidate.model_copy(update={"score": max(0.0, min(1.0, candidate.score + adjustment))}))
        return fitted

    @staticmethod
    def _rank_candidates(candidates: list[AccountCandidate], limit: int = 3) -> list[AccountCandidate]:
        ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        return ranked[:limit]

    @staticmethod
    def _candidate_margin(candidates: list[AccountCandidate]) -> float:
        scores = sorted((candidate.score for candidate in candidates), reverse=True)
        if len(scores) < 2:
            return 0.5 if scores else 0.0
        return min(1.0, max(0.0, (scores[0] - scores[1]) / max(scores[0], 1e-6)))

    @staticmethod
    def _ambiguous_account(candidates: list[AccountCandidate], selected: Any, area: str = "INDETERMINADO") -> bool:
        """Rejects a leaf when retrieval exposes unresolved area/cost-center alternatives."""
        if selected is None or len(candidates) < 2:
            return False
        selected_code = selected.codigo
        selected_candidate = next((candidate for candidate in candidates if candidate.codigo == selected_code), None)
        if selected_candidate is None:
            return False
        selected_area = ClassifierService._area_in_description(selected_candidate.descripcion or "")
        sibling_areas = {ClassifierService._area_in_description(c.descripcion or "") for c in candidates if c.codigo != selected_code}
        if area == "INDETERMINADO" and selected_area and any(other and other != selected_area for other in sibling_areas):
            return True
        if selected_area and area != "INDETERMINADO" and selected_area != area:
            return True
        centers = {
            str(candidate.metadata.get("centro_costos") or "").strip().lower()
            for candidate in candidates
            if candidate.codigo.startswith(selected_code[:4]) and str(candidate.metadata.get("centro_costos") or "").strip()
        }
        if len(centers) > 1 and not selected_candidate.metadata.get("centro_costos"):
            return True
        return ClassifierService._candidate_margin(candidates) < 0.04 and area == "INDETERMINADO"

    @staticmethod
    def _justification(candidates: list[AccountCandidate], selected: Any, label: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if selected is not None:
            candidate = next((item for item in candidates if item.codigo == selected.codigo), None)
            if candidate:
                result.append({
                    "source": candidate.source,
                    "account": candidate.codigo,
                    "reason": f"{label}: {candidate.descripcion or 'candidato recuperado'}; score={candidate.score:.4f}.",
                })
        return result

    @staticmethod
    def _negative_justification(candidates: list[AccountCandidate], selected: Any) -> list[dict[str, Any]]:
        selected_code = selected.codigo if selected is not None else None
        return [
            {
                "source": candidate.source,
                "candidate": candidate.codigo,
                "reason": f"Candidato alternativo con score {candidate.score:.4f}; no supera la evidencia del candidato elegido.",
            }
            for candidate in candidates
            if candidate.codigo != selected_code
        ]

    @staticmethod
    def _legacy_classify(payload: ClassifyRequest, rag, llm, settings: Settings, top_k: int | None) -> ClassificationResponse:
        query = f"{payload.comprobante.libro}\n{ClassifierService._items_text(payload)}"
        hits, rag_conf = rag.search(query, top_k=top_k, facts=ClassifierService._facts(payload))
        evidence = rag.evidence(hits)
        data, _ = llm.generate_json("Devuelve exclusivamente el JSON de clasificación.", json.dumps(payload.model_dump(mode="json"), ensure_ascii=False))
        core = ClassificationCore.model_validate(data)
        grounding_text = "\n".join(h.chunk.content for h in hits)
        for field_name in ("cuenta_base_imponible", "cuenta_total"):
            account = getattr(core, field_name)
            if account and re.search(rf"(?<![A-Za-z0-9]){re.escape(account.codigo)}(?![A-Za-z0-9])", grounding_text) is None:
                setattr(core, field_name, None)
        final_conf = min(float(core.confianza), float(rag_conf))
        return ClassificationResponse(**core.model_dump(exclude={"confianza"}), confianza=round(final_conf, 4), requiere_revision=final_conf < settings.review_threshold, confianza_rag=round(rag_conf, 4), evidencias_rag=evidence)

    def classify(self, payload: ClassifyRequest, top_k: int | None = None, debug: bool = False) -> ClassificationResponse:
        payload = self._resolve_request(payload)
        if not hasattr(self.llm, "interpret_operation"):
            return self._legacy_classify(payload, self.rag, self.llm, self.settings, top_k)

        facts = self._facts(payload)
        context_query = self.build_context_query(payload)
        company_hits = []
        counterparty_hits = []
        if hasattr(self.rag, "retrieve_ciiu_exact"):
            company_hits = [hit for code in facts["company_ciiu"] for hit in self.rag.retrieve_ciiu_exact(code)]
            counterparty_hits = [hit for code in facts["counterparty_ciiu"] for hit in self.rag.retrieve_ciiu_exact(code)]
        supplementary_query = "\n".join([self._items_text(payload), self._activities_text(payload.comprobante.contraparte.actividades_economicas if payload.comprobante.contraparte else [])])
        supplementary_hits, supplementary_conf = self.rag.search(supplementary_query, top_k=3, facts={"counterparty_ciiu": facts["counterparty_ciiu"]}, purpose="context")
        context_hits = company_hits + counterparty_hits + supplementary_hits
        context_conf = 1.0 if company_hits or counterparty_hits else supplementary_conf
        company_ciiu_evidence = self._hit_dicts(self.rag, company_hits)
        counterparty_ciiu_evidence = self._hit_dicts(self.rag, counterparty_hits)
        context_evidence = [
            *[dict(item, evidence_role="company_ciiu") for item in company_ciiu_evidence],
            *[dict(item, evidence_role="counterparty_ciiu") for item in counterparty_ciiu_evidence],
            *[dict(item, evidence_role="supplementary_ciiu") for item in self._hit_dicts(self.rag, supplementary_hits)],
        ]
        operation_payload = payload.model_dump(mode="json", exclude_none=True)
        operation_payload["company_ciiu_evidence"] = company_ciiu_evidence
        operation_payload["counterparty_ciiu_evidence"] = counterparty_ciiu_evidence
        interpretation: OperationInterpretation = self.llm.interpret_operation(operation_payload, context_evidence)
        gemini_operation_interpretation = interpretation.model_dump(mode="json")
        purpose: EconomicPurpose = self.llm.interpret_economic_purpose(operation_payload, gemini_operation_interpretation, context_evidence)
        gemini_economic_purpose = purpose.model_dump(mode="json")
        book = normalize_for_search(payload.comprobante.libro)
        direction = "COMPRA" if book in {"compra", "compras"} else "VENTA" if book in {"venta", "ventas"} else interpretation.direccion
        interpretation = interpretation.model_copy(update={"direccion": direction})

        base_query = self.build_base_account_query(interpretation, purpose)
        account_facts = {"libro": facts["libro"], "tipo_cp": facts["tipo_cp"], "operation_text": interpretation.concepto, "operation_nature": interpretation.naturaleza, "area_funcional": purpose.area_funcional}
        concept_terms = [token for token in tokenize(interpretation.concepto) if len(token) > 3 and token not in {"servicio", "servicios", "compra", "venta", "emision"}]
        family_queries = [base_query] + concept_terms[:3]
        if hasattr(self.rag, "search_multi"):
            family_hits, family_conf = self.rag.search_multi(family_queries, top_k=self.settings.rag_candidate_pool, facts=account_facts, purpose="base_account")
        else:
            family_hits, family_conf = self.rag.search(base_query, top_k=self.settings.rag_candidate_pool, facts=account_facts, purpose="base_account")
        family_terms = " ".join(hit.chunk.content[:500] for hit in family_hits[:3])
        leaf_query = f"{base_query}\nFAMILIAS Y JERARQUIA:\n{family_terms}\nAREA FUNCIONAL: {purpose.area_funcional}"
        base_hits, base_conf = self.rag.search(leaf_query, top_k=self.settings.rag_candidate_pool, facts=account_facts, purpose="base_account_leaf")
        total_query = self.build_total_account_query(payload, interpretation.direccion)
        total_family_hits, total_family_conf = self.rag.search(total_query, top_k=self.settings.rag_candidate_pool, facts=account_facts, purpose="total_account")
        total_family_terms = " ".join(hit.chunk.content[:500] for hit in total_family_hits[:3])
        total_leaf_query = f"{total_query}\nJERARQUIA DE CUENTA TOTAL:\n{total_family_terms}"
        total_hits, total_conf = self.rag.search(total_leaf_query, top_k=self.settings.rag_candidate_pool, facts=account_facts, purpose="total_account")
        base_candidates_raw = self._account_candidates(family_hits + base_hits, account_facts, "base_account")
        if hasattr(self.rag, "account_siblings"):
            sibling_hits = self.rag.account_siblings([c.codigo for c in base_candidates_raw], account_facts)
            base_hits += sibling_hits
        if hasattr(self.rag, "account_descendants"):
            base_hits += self.rag.account_descendants(base_query, interpretation.direccion, interpretation.naturaleza, purpose.area_funcional, "base_account")
            total_hits += self.rag.account_descendants(total_query, interpretation.direccion, interpretation.naturaleza, purpose.area_funcional, "total_account")
        base_candidates_raw = self._account_candidates(base_hits, account_facts, "base_account")
        total_candidates_raw = self._account_candidates(total_hits, account_facts, "total_account")
        filtered_base = [c for c in base_candidates_raw if self._base_compatible(c, interpretation, purpose)]
        filtered_total = [c for c in total_candidates_raw if self._total_compatible(c, interpretation.direccion)]
        filtered_base = self._apply_document_fit(filtered_base, payload, interpretation, purpose, "base_account")
        filtered_total = self._apply_document_fit(filtered_total, payload, interpretation, purpose, "total_account")
        base_candidates = self._rank_candidates(filtered_base)
        total_candidates = self._rank_candidates(filtered_total)
        selected_before_final_gemini = {
            "base": base_candidates[0].model_dump() if base_candidates else None,
            "total": total_candidates[0].model_dump() if total_candidates else None,
        }
        interpretation_data = {**interpretation.model_dump(mode="json"), "finalidad_economica": purpose.model_dump(mode="json")}
        selected_base_codes = {c.codigo for c in base_candidates}
        selected_total_codes = {c.codigo for c in total_candidates}
        base_evidence_hits = [h for h in base_hits if (candidate := self._candidate_from_hit(h, account_facts, "base_account")) and candidate.codigo in selected_base_codes][:3]
        total_evidence_hits = [h for h in total_hits if (candidate := self._candidate_from_hit(h, account_facts, "total_account")) and candidate.codigo in selected_total_codes][:3]
        tax_hits = self.rag.search_tax(f"{interpretation.direccion} {payload.comprobante.tipo_cp.descripcion or payload.comprobante.tipo_cp.codigo} {self._amount_condition(payload)} IGV") if hasattr(self.rag, "search_tax") else []
        staged_evidence = [{
            "context_evidence": context_evidence,
            "base_account_evidence": self._hit_dicts(self.rag, base_evidence_hits),
            "total_account_evidence": self._hit_dicts(self.rag, total_evidence_hits),
            "tax_evidence": self._hit_dicts(self.rag, tax_hits),
        }]
        core = self.llm.classify_with_candidates(operation_payload, interpretation_data, [c.model_dump() for c in base_candidates], [c.model_dump() for c in total_candidates], staged_evidence)
        gemini_final_response = core.model_dump(mode="json")
        context_sources = sorted({str(item.get("source")) for item in context_evidence if item.get("source")})
        core.razon = (
            f"{interpretation.concepto}: {interpretation.razon} "
            f"Evidencia contextual RAG: {', '.join(context_sources) or 'sin evidencia contextual suficiente'}."
        ) + " " + core.razon

        candidate_codes = {c.codigo for c in base_candidates + total_candidates}
        discarded: list[str] = []
        allowed_codes = {
            "cuenta_base_imponible": {c.codigo for c in base_candidates},
            "cuenta_total": {c.codigo for c in total_candidates},
        }
        ambiguity: list[str] = []
        for field_name in ("cuenta_base_imponible", "cuenta_total"):
            account = getattr(core, field_name)
            if account and account.codigo not in allowed_codes[field_name]:
                discarded.append(f"{field_name}={account.codigo}")
                setattr(core, field_name, None)
        selected_after_grounding = {
            "base": core.cuenta_base_imponible.model_dump() if core.cuenta_base_imponible else None,
            "total": core.cuenta_total.model_dump() if core.cuenta_total else None,
        }
        for field_name in ("cuenta_base_imponible",):
            account = getattr(core, field_name)
            if account and self._ambiguous_account(base_candidates_raw, account, purpose.area_funcional):
                ambiguity.append(f"{field_name}={account.codigo}")
                setattr(core, field_name, None)
        selected_after_ambiguity = {
            "base": core.cuenta_base_imponible.model_dump() if core.cuenta_base_imponible else None,
            "total": core.cuenta_total.model_dump() if core.cuenta_total else None,
        }
        core.condicion_igv = self._amount_condition(payload)

        margin = min(self._candidate_margin(base_candidates), self._candidate_margin(total_candidates))
        components = ConfidenceComponents(
            interpretation=min(interpretation.confianza_interpretacion, purpose.nivel_confianza),
            retrieval_quality=(context_conf + base_conf + total_conf) / 3,
            evidence_coherence=min(context_conf, base_conf if base_candidates else 0, total_conf if total_candidates else 0),
            base_account_support=1.0 if core.cuenta_base_imponible else 0.0,
            total_account_support=1.0 if core.cuenta_total else 0.0,
            completeness=1.0 if core.cuenta_base_imponible and core.cuenta_total else 0.55,
            candidate_margin=margin,
        )
        weights = {"interpretation": .20, "retrieval_quality": .15, "evidence_coherence": .15, "base_account_support": .18, "total_account_support": .15, "completeness": .10, "candidate_margin": .07}
        confidence = math.prod(max(getattr(components, name), 0.01) ** weight for name, weight in weights.items())
        confidence = min(float(core.confianza), confidence)
        if discarded or ambiguity:
            confidence *= 0.5
            reasons = []
            if discarded:
                reasons.append("grounding: " + ", ".join(discarded))
            if ambiguity:
                reasons.append("ambigüedad de candidatos: " + ", ".join(ambiguity))
            core.razon = core.razon.rstrip() + " " + "; ".join(reasons) + "."
        if core.cuenta_base_imponible:
            core.razon = core.razon.rstrip() + f" Evidencia cuenta base: {core.cuenta_base_imponible.codigo} recuperada desde " + ", ".join(sorted({c.source or 'fuente RAG' for c in base_candidates if c.codigo == core.cuenta_base_imponible.codigo})) + "."
        if core.cuenta_total:
            core.razon = core.razon.rstrip() + f" Evidencia cuenta total: {core.cuenta_total.codigo} recuperada desde " + ", ".join(sorted({c.source or 'fuente RAG' for c in total_candidates if c.codigo == core.cuenta_total.codigo})) + "."
        requires_review = confidence < self.settings.review_threshold or not core.cuenta_base_imponible or not core.cuenta_total or purpose.area_funcional == "INDETERMINADO" or bool(discarded) or bool(ambiguity)
        all_evidence = self._hit_dicts(self.rag, context_hits + base_evidence_hits + total_evidence_hits + tax_hits)
        debug_data = None
        if debug:
            debug_data = {
                "input_real_received": payload.model_dump(mode="json", exclude_none=True),
                "company_ciiu_codes": facts["company_ciiu"],
                "counterparty_ciiu_codes": facts["counterparty_ciiu"],
                "exact_ciiu_evidence": [
                    {"code": item.get("metadata", {}).get("ciiu"), "source": item.get("source"), "matched_text": item.get("snippet")}
                    for item in company_ciiu_evidence + counterparty_ciiu_evidence
                ],
                "company_head_used": payload.empresa.model_dump(mode="json") if payload.empresa else None,
                "counterparty_head_used": payload.comprobante.contraparte.model_dump(mode="json") if payload.comprobante.contraparte else None,
                "context_query": context_query,
                "company_ciiu_evidence": company_ciiu_evidence,
                "counterparty_ciiu_evidence": counterparty_ciiu_evidence,
                "context_hits": context_evidence,
                "operation_interpretation": interpretation.model_dump(mode="json"),
                "economic_purpose": purpose.model_dump(mode="json"),
                "gemini_operation_interpretation_raw": gemini_operation_interpretation,
                "gemini_economic_purpose_raw": gemini_economic_purpose,
                "normalized_direction": direction,
                "account_family_candidates": [c.model_dump() for c in self._account_candidates(family_hits, account_facts, "base_account")[:10]],
                "account_family": (base_candidates[0].codigo[:4] if base_candidates and len(base_candidates[0].codigo) >= 4 else None),
                "family_children": [c.model_dump() for c in base_candidates_raw if base_candidates and c.codigo.startswith(base_candidates[0].codigo[:4]) and len(c.codigo) > 4],
                "base_account_candidates": [c.model_dump() for c in base_candidates],
                "total_account_candidates": [c.model_dump() for c in total_candidates],
                "base_account_query": base_query,
                "raw_base_candidates": [c.model_dump() for c in base_candidates_raw[:10]],
                "filtered_base_candidates": [c.model_dump() for c in self._rank_candidates(filtered_base, 10)],
                "reranked_base_candidates": [c.model_dump() for c in base_candidates],
                "base_account_candidates_raw_top10": [c.model_dump() for c in base_candidates_raw[:10]],
                "total_account_query": total_query,
                "raw_total_candidates": [c.model_dump() for c in total_candidates_raw[:10]],
                "filtered_total_candidates": [c.model_dump() for c in self._rank_candidates(filtered_total, 10)],
                "reranked_total_candidates": [c.model_dump() for c in total_candidates],
                "total_family": "42" if direction == "COMPRA" else "12" if direction == "VENTA" else None,
                "total_family_children": [c.model_dump() for c in total_candidates_raw if c.codigo.startswith("42" if direction == "COMPRA" else "12")],
                "selected_before_final_gemini": selected_before_final_gemini,
                "candidates_sent_to_final_gemini": {"base": [c.model_dump() for c in base_candidates], "total": [c.model_dump() for c in total_candidates]},
                "gemini_final_response": gemini_final_response,
                "selected_after_grounding": selected_after_grounding,
                "selected_after_ambiguity": selected_after_ambiguity,
                "selected_after_confidence": {"base": core.cuenta_base_imponible.model_dump() if core.cuenta_base_imponible else None, "total": core.cuenta_total.model_dump() if core.cuenta_total else None, "confidence": round(confidence, 4)},
                "selected_base": core.cuenta_base_imponible.model_dump() if core.cuenta_base_imponible else None,
                "selected_total": core.cuenta_total.model_dump() if core.cuenta_total else None,
                "context_evidence": context_evidence,
                "base_account_evidence": staged_evidence[0]["base_account_evidence"],
                "total_account_evidence": staged_evidence[0]["total_account_evidence"],
                "tax_evidence": staged_evidence[0]["tax_evidence"],
                "total_account_family_raw_top10": [
                    {"source": hit.chunk.source, "score": round(hit.score, 4), "snippet": hit.chunk.content[:300]}
                    for hit in total_family_hits[:10]
                ],
                "total_account_candidates_raw_top10": [c.model_dump() for c in total_candidates_raw[:10]],
                "rag_justification": {
                    "operation_evidence": [
                        {"source": item.get("source"), "reason": "Evidencia recuperada para interpretar la operación."}
                        for item in context_evidence
                    ],
                    "base_account_evidence": self._justification(base_candidates, core.cuenta_base_imponible, "Candidato de cuenta base"),
                    "total_account_evidence": self._justification(total_candidates, core.cuenta_total, "Candidato de cuenta total"),
                    "negative_evidence": self._negative_justification(base_candidates, core.cuenta_base_imponible)
                    + self._negative_justification(total_candidates, core.cuenta_total)
                    + [
                        {"candidate": code, "reason": "Descartado por falta de grounding o evidencia suficiente."}
                        for code in discarded + ambiguity
                    ],
                },
                "confidence_components": components.model_dump(),
                "gemini_model": self.settings.gemini_model,
                "final_validation": {"discarded": discarded, "ambiguous": ambiguity, "candidate_codes": sorted(candidate_codes)},
            }
        return ClassificationResponse(**core.model_dump(exclude={"confianza"}), confianza=round(confidence, 4), requiere_revision=requires_review, confianza_rag=round(min(context_conf, base_conf, total_conf), 4), evidencias_rag=all_evidence, debug=debug_data)

