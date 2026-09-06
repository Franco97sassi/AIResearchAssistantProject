from __future__ import annotations

import re
from dataclasses import dataclass

from app.guardrails import answer_has_required_sources, inspect_text
from app.rag import SearchResult
from app.tokens import estimate_tokens


@dataclass(frozen=True)
class RAGEvaluation:
    faithfulness: float
    context_precision: float
    context_recall_proxy: float
    hallucination_risk: str
    grounded: bool
    source_coverage: float
    pii_detected: bool
    prompt_injection_detected: bool
    estimated_answer_tokens: int
    notes: list[str]


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-záéíóúñü0-9]+", text.lower()) if len(term) > 3}


def evaluate_rag_response(
    *,
    question: str,
    answer: str,
    sources: list[SearchResult],
) -> RAGEvaluation:
    """Run deterministic, free RAG checks without LLM-as-a-judge dependencies."""
    answer_terms = _terms(answer)
    question_terms = _terms(question)
    source_terms = _terms(" ".join(source.text for source in sources))
    cited = answer_has_required_sources(answer, len(sources))
    grounded_terms = answer_terms & source_terms
    unsupported_terms = answer_terms - source_terms - question_terms

    source_coverage = len(grounded_terms) / max(1, len(answer_terms))
    context_precision = len(source_terms & question_terms) / max(1, len(source_terms))
    context_recall_proxy = len(question_terms & source_terms) / max(1, len(question_terms))
    faithfulness = min(1.0, source_coverage + (0.15 if cited else 0.0))

    guardrail = inspect_text(answer)
    if not sources:
        risk = "high" if answer_terms else "low"
    elif not cited or source_coverage < 0.25 or len(unsupported_terms) > len(grounded_terms) * 2:
        risk = "medium"
    else:
        risk = "low"

    notes: list[str] = []
    if not sources:
        notes.append("No hay fuentes recuperadas para validar grounding.")
    if sources and not cited:
        notes.append("La respuesta no menciona fuente o pagina explicitamente.")
    if unsupported_terms:
        notes.append(
            "Hay terminos de la respuesta que no aparecen en la pregunta ni en las fuentes."
        )
    if guardrail.violations:
        notes.append("La respuesta contiene señales de seguridad que deben revisarse.")

    return RAGEvaluation(
        faithfulness=round(faithfulness, 3),
        context_precision=round(context_precision, 3),
        context_recall_proxy=round(context_recall_proxy, 3),
        hallucination_risk=risk,
        grounded=bool(sources) and cited and risk == "low",
        source_coverage=round(source_coverage, 3),
        pii_detected=bool(
            guardrail.pii["emails"] or guardrail.pii["phones"] or guardrail.pii["cards"]
        ),
        prompt_injection_detected=guardrail.prompt_injection,
        estimated_answer_tokens=estimate_tokens(answer),
        notes=notes,
    )
