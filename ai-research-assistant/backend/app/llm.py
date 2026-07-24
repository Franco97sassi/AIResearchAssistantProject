from dataclasses import dataclass

from groq import Groq

from app.config import (
    GROQ_API_KEY,
    GROQ_MODEL,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    LLM_TOP_P,
    MAX_CONTEXT_TOKENS,
)
from app.langchain_rag import build_langchain_rag_prompt
from app.rag import SearchResult
from app.tokens import estimate_tokens, truncate_to_token_budget

@dataclass(frozen=True)
class RAGAnswer:
    answer: str
    model: str
    used_llm: bool
    estimated_prompt_tokens: int
    included_contexts: int

def _format_context_sources(contexts: list[SearchResult]) -> str:
    formatted_chunks: list[str] = []
    for index, context in enumerate(contexts, start=1):
        source_label = (
            f"Fuente {index}: {context.filename}, pagina {context.page_number}"
        )
        formatted_chunks.append(f"[{source_label}]\n{context.text}")
    return "\n\n".join(formatted_chunks)


def _format_chat_history(history: list[dict] | None) -> str:
    if not history:
        return "Sin historial previo."

    formatted_turns = []
    for index, message in enumerate(history, start=1):
        question = str(message.get("question", "")).strip()
        answer = str(message.get("answer", "")).strip()
        formatted_turns.append(
            f"Turno {index}\nUsuario: {question}\nAsistente: {answer}"
        )
    return "\n\n".join(formatted_turns)


def _copy_context_with_text(context: SearchResult, text: str) -> SearchResult:
    return SearchResult(
        text=text,
        filename=context.filename,
        page_number=context.page_number,
        document_id=context.document_id,
        distance=context.distance,
    )

def _select_contexts_for_budget(
    question: str,
    contexts: list[SearchResult],
    history_block: str,
    system_prompt: str,
) -> tuple[list[SearchResult], int]:
    """Keep retrieved chunks inside the configured context-window budget."""
    prompt_without_context = (
        f"{system_prompt}\n\n"
        f"Pregunta: {question}\n\n"
        f"Historial reciente de la conversacion:\n{history_block}\n\n"
        "Contexto recuperado de PDFs:\n"
    )
    fixed_tokens = estimate_tokens(prompt_without_context)
    remaining_tokens = max(0, MAX_CONTEXT_TOKENS - fixed_tokens)
    selected_contexts: list[SearchResult] = []

    for context in contexts:
        formatted_context = _format_context_sources([context])
        context_tokens = estimate_tokens(formatted_context)
        if context_tokens <= remaining_tokens:
            selected_contexts.append(context)
            remaining_tokens -= context_tokens
            continue

        if remaining_tokens > 25:
            source_label = f"Fuente 1: {context.filename}, pagina {context.page_number}"
            label_tokens = estimate_tokens(f"[{source_label}]\n")
            text_budget = max(0, remaining_tokens - label_tokens)
            truncated_text = truncate_to_token_budget(context.text, text_budget)
            if truncated_text:
                selected_contexts.append(
                    _copy_context_with_text(context, truncated_text)
                )
        break

    context_block = _format_context_sources(selected_contexts)
    
    full_prompt = (
        f"{prompt_without_context}{context_block or 'Sin contexto recuperado.'}"
    )
    return selected_contexts, estimate_tokens(full_prompt)
def _build_local_answer(
    question: str,
    contexts: list[SearchResult],
    history: list[dict] | None = None,
    ) -> str:
    if not contexts:
        return (
            "No encontre fragmentos relevantes en los PDFs indexados para responder "
            f"la pregunta: {question}"
        )

    memory_note = ""
    if history:
          memory_note = "La memoria conversacional esta activa y se uso para recuperar contexto.\n\n"

    source_summaries = []
    for context in contexts:
        source_summaries.append(
            f"- {context.text} "
            f"(fuente: {context.filename}, pagina {context.page_number})"
        )

    return (
        "Respuesta preliminar basada en los fragmentos recuperados. "
        "Configura GROQ_API_KEY para activar una respuesta generativa completa.\n\n"
        + memory_note
        + "\n".join(source_summaries)
    )


def generate_rag_answer(
    question: str,
    contexts: list[SearchResult],
    history: list[dict] | None = None,
) -> RAGAnswer:
    """Generate an answer grounded in retrieved PDF chunks and chat memory."""
    normalized_question = question.strip()
    history_block = _format_chat_history(history)
    system_prompt = (
        "Eres un asistente de investigacion academica. Responde en espanol, "
        "usa unicamente el contexto proporcionado y el historial reciente cuando "
        "ayude a entender la pregunta, y cita las fuentes con el formato "
        "(archivo, pagina). Si el contexto no contiene la respuesta, di claramente "
        "que no hay informacion suficiente. Estructura respuestas largas con "
        "titulos o bullets breves."
    )
    selected_contexts, estimated_prompt_tokens = _select_contexts_for_budget(
        normalized_question, contexts, history_block, system_prompt
    )
    if LLM_PROVIDER != "groq" or not GROQ_API_KEY:
         return RAGAnswer(
            answer=_build_local_answer(normalized_question, selected_contexts, history),
            model=f"{LLM_PROVIDER}-local-context-fallback",            used_llm=False,
            estimated_prompt_tokens=estimated_prompt_tokens,
            included_contexts=len(selected_contexts),
        )

    context_block = _format_context_sources(selected_contexts)
    prompt = build_langchain_rag_prompt(
        system_prompt=system_prompt,
        question=normalized_question,
        history_block=history_block,
        context_block=context_block or "Sin contexto recuperado.",
    )
    user_prompt = (
        prompt["user"]
        if isinstance(prompt, dict)
        else prompt.format_messages(
            question=normalized_question,
            history_block=history_block,
            context_block=context_block or "Sin contexto recuperado.",
        )[1].content    )

    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            top_p=LLM_TOP_P,
        )
        answer = completion.choices[0].message.content or ""
    except Exception as error:
        return RAGAnswer(
            answer=(
                _build_local_answer(normalized_question, selected_contexts, history)
                + "\n\nNo se pudo contactar el modelo configurado en Groq. "
                + f"Detalle tecnico: {type(error).__name__}."
            ),
            model="local-context-fallback",
            used_llm=False,
            estimated_prompt_tokens=estimated_prompt_tokens,
            included_contexts=len(selected_contexts),
        )

    return RAGAnswer(
        answer=answer.strip(),
        model=GROQ_MODEL,
        used_llm=True,
        estimated_prompt_tokens=estimated_prompt_tokens,
        included_contexts=len(selected_contexts),
    )
