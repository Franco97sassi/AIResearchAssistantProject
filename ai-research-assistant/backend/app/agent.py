from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypedDict

from app.chat_history import build_retrieval_query
from app.llm import RAGAnswer, generate_rag_answer
from app.rag import SearchResult, search_similar_chunks
from langgraph.graph import END, StateGraph


@dataclass(frozen=True)
class AgentStep:
    """Single visible step in the agent reasoning/control flow."""

    name: str
    description: str
    tool: str | None = None
    decision: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class AgentRun:
    """Result produced by the research agent."""

    answer: str
    model: str
    used_llm: bool
    sources: list[SearchResult]
    steps: list[AgentStep] = field(default_factory=list)
    framework: str = "langgraph-multiagent"
    estimated_prompt_tokens: int = 0
    included_contexts: int = 0


SearchTool = Callable[[str, int], list[SearchResult]]
AnswerTool = Callable[[str, list[SearchResult], list[dict] | None], RAGAnswer]
NextNode = Literal["buscar", "responder"]


class ResearchAgentState(TypedDict):
    """State shared by the real LangGraph research-agent nodes."""

    question: str
    normalized_question: str
    history: list[dict]
    limit: int
    search_tool: SearchTool
    answer_tool: AnswerTool
    steps: list[AgentStep]
    needs_search: bool
    retrieval_query: str
    results: list[SearchResult]
    verified_sources: list[SearchResult]
    context_is_relevant: bool
    rag_answer: RAGAnswer | None


_GREETING_WORDS = {
    "hola",
    "buenas",
    "gracias",
    "ok",
    "okay",
    "hello",
    "hi",
}


def _needs_document_search(question: str) -> bool:
    normalized = question.strip().lower().strip("¿?!. ")
    return normalized not in _GREETING_WORDS and len(normalized) > 2


def _build_no_search_answer(question: str) -> RAGAnswer:
    return RAGAnswer(
        answer=(
            "Hola. Soy el agente de investigacion: puedo buscar en tus PDFs, "
            "usar la herramienta de recuperacion semantica y decidir que fuentes "
            "citar. Hazme una pregunta concreta sobre un documento indexado."
        ),
        model="local-agent-router",
        used_llm=False,
        estimated_prompt_tokens=0,
        included_contexts=0,
    )


def _append_step(state: ResearchAgentState, step: AgentStep) -> list[AgentStep]:
    return [*state["steps"], step]


def _content_terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-záéíóúñü0-9]+", text.lower()) if len(term) > 3}


def _think_node(state: ResearchAgentState) -> dict:
    recent_history = state["history"]
    return {
        "normalized_question": state["question"].strip(),
        "steps": _append_step(
            state,
            AgentStep(
                name="pensar",
                description="Normalizo la pregunta y reviso si el historial ayuda a entenderla.",
                decision="usar_historial" if recent_history else "sin_historial_previo",
                role="Coordinador",
            ),
        ),
    }


def _decide_node(state: ResearchAgentState) -> dict:
    needs_search = _needs_document_search(state["normalized_question"])
    decision = "buscar_en_vector_db" if needs_search else "no_buscar"
    description = (
        "La pregunta necesita evidencia documental antes de responder."
        if needs_search
        else "La entrada parece un saludo o no requiere buscar documentos."
    )
    retrieval_query = (
        build_retrieval_query(state["normalized_question"], state["history"])
        if needs_search
        else ""
    )
    return {
        "needs_search": needs_search,
        "retrieval_query": retrieval_query,
        "steps": _append_step(
            state,
            AgentStep(
                name="decidir",
                description=description,
                decision=decision,
                role="Coordinador",
            ),
        ),
    }


def _route_after_decide(state: ResearchAgentState) -> NextNode:
    return "buscar" if state["needs_search"] else "responder"


def _search_node(state: ResearchAgentState) -> dict:
    results = state["search_tool"](state["retrieval_query"], state["limit"])
    return {
        "results": results,
        "steps": _append_step(
            state,
            AgentStep(
                name="buscar",
                description=f"Recupere {len(results)} fragmentos relevantes desde ChromaDB.",
                tool="search_similar_chunks",
                decision="contexto_recuperado" if results else "sin_resultados",
                role="Investigador",
            ),
        ),
    }


def _evaluate_context_node(state: ResearchAgentState) -> dict:
    results = state["results"]
    question_terms = _content_terms(state["normalized_question"])
    context_terms = _content_terms(" ".join(result.text for result in results))
    context_is_relevant = bool(results) and (
        not question_terms or bool(question_terms & context_terms)
    )
    decision = (
        "contexto_relevante"
        if context_is_relevant
        else "contexto_debil"
        if results
        else "contexto_insuficiente"
    )
    return {
        "context_is_relevant": context_is_relevant,
        "steps": _append_step(
            state,
            AgentStep(
                name="evaluar_contexto",
                description=(
                    "El Critico valida que el contexto recuperado responde a la pregunta."
                    if context_is_relevant
                    else "El Critico detecta que el contexto no responde claramente a la pregunta."
                    if results
                    else "El Critico confirma que no hay contexto suficiente para responder."
                ),
                decision=decision,
                role="Critico",
            ),
        ),
    }


def _answer_node(state: ResearchAgentState) -> dict:
    results = state["results"]
    rag_answer = (
        state["answer_tool"](state["normalized_question"], results, state["history"])
        if state["needs_search"]
        else _build_no_search_answer(state["normalized_question"])
    )
    return {
        "rag_answer": rag_answer,
        "steps": _append_step(
            state,
            AgentStep(
                name="responder",
                description=(
                    "Genero una respuesta grounded con fuentes"
                    if results
                    else "Respondo indicando que no hay evidencia suficiente o que no hace falta buscar"
                ),
                tool="generate_rag_answer" if state["needs_search"] else None,
                role="Redactor",
                decision=(
                    "citar_fuentes"
                    if results
                    else "pedir_mas_documentos"
                    if state["needs_search"]
                    else "no_buscar"
                ),
            ),
        ),
    }


def _cite_node(state: ResearchAgentState) -> dict:
    verified_sources = [
        result for result in state["results"] if result.filename.strip() and result.page_number > 0
    ]
    if not state["needs_search"]:
        decision = "sin_fuentes_requeridas"
        description = "El Citador confirma que la respuesta directa no requiere fuentes."
    elif verified_sources and len(verified_sources) == len(state["results"]):
        decision = "fuentes_y_paginas_verificadas"
        description = "El Citador verifica que todas las fuentes incluyen archivo y pagina."
    elif verified_sources:
        decision = "fuentes_parciales"
        description = "El Citador conserva solo las fuentes con archivo y pagina verificables."
    else:
        decision = "sin_fuentes_verificables"
        description = "El Citador no encontro fuentes con archivo y pagina verificables."

    return {
        "verified_sources": verified_sources,
        "steps": _append_step(
            state,
            AgentStep(
                name="verificar_citas",
                description=description,
                decision=decision,
                role="Citador",
            ),
        ),
    }


def _build_research_graph():
    graph = StateGraph(ResearchAgentState)
    graph.add_node("pensar", _think_node)
    graph.add_node("decidir", _decide_node)
    graph.add_node("buscar", _search_node)
    graph.add_node("evaluar_contexto", _evaluate_context_node)
    graph.add_node("responder", _answer_node)
    graph.add_node("verificar_citas", _cite_node)
    graph.add_edge("responder", "verificar_citas")
    graph.add_edge("verificar_citas", END)
    graph.set_entry_point("pensar")
    graph.add_edge("pensar", "decidir")
    graph.add_conditional_edges(
        "decidir",
        _route_after_decide,
        {"buscar": "buscar", "responder": "responder"},
    )
    graph.add_edge("buscar", "evaluar_contexto")
    graph.add_edge("evaluar_contexto", "responder")
    return graph.compile()


_RESEARCH_GRAPH = _build_research_graph()


def run_research_agent(
    *,
    question: str,
    history: list[dict] | None = None,
    limit: int = 4,
    document_id: str | None = None,
    search_tool: SearchTool = search_similar_chunks,
    answer_tool: AnswerTool = generate_rag_answer,
) -> AgentRun:
    """Run the PDF research agent as a real LangGraph state graph."""

    def scoped_search_tool(query: str, result_limit: int) -> list[SearchResult]:
        if document_id:
            return search_similar_chunks(
                query,
                limit=result_limit,
                document_id=document_id,
            )
        return search_tool(query, result_limit)

    initial_state: ResearchAgentState = {
        "question": question,
        "normalized_question": "",
        "history": history or [],
        "limit": limit,
        "search_tool": scoped_search_tool,
        "answer_tool": answer_tool,
        "steps": [],
        "needs_search": False,
        "retrieval_query": "",
        "results": [],
        "verified_sources": [],
        "context_is_relevant": False,
        "rag_answer": None,
    }
    final_state = _RESEARCH_GRAPH.invoke(initial_state)
    rag_answer = final_state["rag_answer"]
    if rag_answer is None:
        rag_answer = _build_no_search_answer(final_state["normalized_question"])

    return AgentRun(
        answer=rag_answer.answer,
        model=rag_answer.model,
        used_llm=rag_answer.used_llm,
        sources=final_state.get("verified_sources") or final_state["results"],
        steps=final_state["steps"],
        estimated_prompt_tokens=rag_answer.estimated_prompt_tokens,
        included_contexts=rag_answer.included_contexts,
    )
