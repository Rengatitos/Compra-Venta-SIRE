"""Etapas del clasificador: interpretación, candidatos y selección (portado de su API original)."""

from pathlib import Path

from app.services.clasificador.classifier import ClassifierService
from app.services.clasificador.config import Settings
from app.services.clasificador.documents import DocumentLoader
from app.services.clasificador.rag import HybridRAG
from app.services.clasificador.schemas import (
    ClassificationCore,
    ClassifyRequest,
    EconomicPurpose,
    OperationInterpretation,
    RAGEvidence,
)


class Hit:
    def __init__(self, content, source, code=None, score=0.8):
        self.score = score
        self.semantic_score = score
        self.lexical_score = score
        self.metadata_score = score
        self.chunk = type("Chunk", (), {
            "content": content,
            "source": source,
            "source_weight": 1.0,
            "metadata": ({"cuenta": code, "descripcion": content} if code else {}),
        })()


class StagedRAG:
    def __init__(self):
        self.calls = []

    def search(self, query, top_k=None, facts=None, purpose=None):
        self.calls.append(purpose)
        if purpose == "context":
            return [Hit("CIIU 6920 actividades contables", "ciiu/notas.pdf")], 0.8
        if purpose in {"base_account", "base_account_leaf"}:
            return [Hit("Cuenta 6311 servicios profesionales", "plan_cuentas/compras.xlsx", "6311")], 0.8
        return [Hit("Cuenta 4212 proveedores terceros", "plan_cuentas/compras.xlsx", "4212")], 0.8

    def evidence(self, hits):
        return [RAGEvidence(
            source=h.chunk.source, score=h.score, semantic_score=h.semantic_score,
            lexical_score=h.lexical_score, metadata_score=h.metadata_score,
            source_weight=1.0, snippet=h.chunk.content, metadata=h.chunk.metadata,
        ) for h in hits]


class StagedGemini:
    def __init__(self):
        self.calls = []

    def interpret_operation(self, payload, context_hits):
        self.calls.append("interpret")
        return OperationInterpretation(
            direccion="COMPRA", naturaleza="SERVICIO", concepto="SERVICIO CONTABLE",
            tipo_operacion="COMPRA_LOCAL", destino_probable="GASTO",
            actividad_contraparte_relevante={"ciiu_v4": "6920", "descripcion": "Contabilidad"},
            confianza_interpretacion=0.9, razon="La actividad compatible respalda el servicio.",
        )

    def classify_with_candidates(self, payload, interpretation, base_candidates, total_candidates, context_hits):
        self.calls.append("select")
        return ClassificationCore(
            clasificacion="COMPRA / SERVICIO", subtipo="SERVICIO CONTABLE",
            cuenta_base_imponible={"codigo": base_candidates[0]["codigo"], "descripcion": base_candidates[0]["descripcion"]},
            cuenta_total={"codigo": total_candidates[0]["codigo"], "descripcion": total_candidates[0]["descripcion"]},
            condicion_igv="GRAVADO", confianza=0.95, razon="Candidatos respaldados por RAG.",
        )

    def interpret_economic_purpose(self, payload, interpretation, context_hits):
        self.calls.append("purpose")
        return EconomicPurpose(area_funcional="ADMINISTRACION", tratamiento_contable="GASTO", nivel_confianza=0.9, razon="Soporte administrativo.")


def request(importes):
    return {
        "empresa": {"ruc": "20610202251", "actividades_economicas": [{"ciiu": "4663"}]},
        "comprobante": {"libro": "COMPRAS", "tipo_cp": {"codigo": "01"}, "importes": importes,
                        "contraparte": {"numero_documento": "20486339510", "actividades_economicas": [{"ciiu": "6920"}]}},
        "items": [{"descripcion": "SERVICIO CONTABLE"}],
    }


def test_staged_pipeline_and_deterministic_tax_condition(tmp_path: Path):
    settings = Settings.from_env(tmp_path)
    rag = StagedRAG()
    gemini = StagedGemini()
    service = ClassifierService(settings, rag, gemini)

    result = service.classify(ClassifyRequest.model_validate(request({"base_imponible": 1750, "igv": 315, "total": 2065})))
    assert rag.calls == ["context", "base_account", "base_account_leaf", "total_account", "total_account"]
    assert gemini.calls == ["interpret", "purpose", "select"]
    # 6311 es una cuenta padre: no se puede imputar y no llega a Gemini. La
    # búsqueda directa en el plan aporta la divisionaria de «SERVICIO CONTABLE»
    # para el área administrativa.
    assert result.cuenta_base_imponible.codigo == "6323094"
    assert result.cuenta_total.codigo == "4212"
    assert result.condicion_igv == "GRAVADO"

    exonerated = ClassifierService._amount_condition(
        ClassifyRequest.model_validate(request({"base_imponible": 0, "igv": 0, "exonerado": 44000, "total": 44000}))
    )
    assert exonerated == "EXONERADO"


def test_functional_area_ranks_accounting_leaf_without_prior_records():
    facts = {"operation_text": "SERVICIO CONTABLE", "operation_nature": "SERVICIO", "area_funcional": "ADMINISTRACION", "company_ciiu": ["4663"], "counterparty_ciiu": ["6920"]}
    hits = [Hit(f"AUDITORIA Y CONTABLE - {suffix}", "plan_cuentas/PLAN_DE_CUENTAS_CONTASIS.xlsx", code) for code, suffix in [
        ("6323090", "PROD"), ("6323093", "CDS"), ("6323094", "ADM"), ("6323095", "VTAS")
    ]]
    candidates = ClassifierService._rank_candidates([ClassifierService._candidate_from_hit(hit, facts, "base_account") for hit in hits], 4)
    assert candidates[0].codigo == "6323094"
    assert candidates[0].score_components["functional_area"] == 1.0
    assert ClassifierService._ambiguous_account(candidates, candidates[0], "ADMINISTRACION") is False
    assert ClassifierService._ambiguous_account(candidates, candidates[0], "INDETERMINADO") is True


def test_prior_records_directory_is_never_indexed(tmp_path: Path):
    allowed = tmp_path / "plan_cuentas" / "plan.txt"
    excluded = tmp_path / "historico" / "asientos.txt"
    allowed.parent.mkdir()
    excluded.parent.mkdir()
    allowed.write_text("6323 auditoria", encoding="utf-8")
    excluded.write_text("cuenta usada", encoding="utf-8")
    assert DocumentLoader(tmp_path).list_documents() == [allowed]
    assert HybridRAG._purpose_allowed("historico/asientos.txt", "base_account") is False


def test_el_area_solo_hace_ambigua_una_cuenta_con_variantes_por_area():
    from app.services.clasificador.schemas import AccountCandidate

    def candidato(codigo, descripcion, score):
        return AccountCandidate(codigo=codigo, descripcion=descripcion, score=score)

    # Combustible: la finalidad no se sabe, pero la cuenta es la misma para
    # cualquier área. Antes el motor la anulaba igual.
    suministros = [
        candidato("603202521", "SUMINISTROS COMBUSTIBLES - Compras", 0.70),
        candidato("603202522", "SUMINISTROS LUBRICANTES - Compras", 0.69),
    ]
    assert ClassifierService._ambiguous_account(suministros, suministros[0], "INDETERMINADO") is False
    assert ClassifierService._depende_del_area(suministros[0], suministros) is False

    # Internet sí cambia de cuenta según el área: sin área, sigue siendo dudoso.
    internet = [
        candidato("6365094", "INTERNET - ADM - Servicios Básicos", 0.70),
        candidato("6365095", "INTERNET - VTAS - Servicios Básicos", 0.69),
    ]
    assert ClassifierService._ambiguous_account(internet, internet[0], "INDETERMINADO") is True
    assert ClassifierService._depende_del_area(internet[0], internet) is True
