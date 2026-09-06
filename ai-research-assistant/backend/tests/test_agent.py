from app.agent import run_research_agent
from app.llm import RAGAnswer
from app.rag import SearchResult


def test_research_agent_searches_and_records_steps():
    calls = {}
    fake_results = [
        SearchResult(
            text="Los agentes usan herramientas para buscar evidencia.",
            filename="agents.pdf",
            page_number=3,
            document_id="doc-agent",
            distance=0.09,
        )
    ]

    def fake_search_tool(question: str, limit: int):
        calls["question"] = question
        calls["limit"] = limit
        return fake_results

    def fake_answer_tool(question: str, contexts: list[SearchResult], history: list[dict] | None):
        return RAGAnswer(
            answer="Un agente piensa, busca y decide con herramientas.",
            model="test-agent-model",
            used_llm=True,
            estimated_prompt_tokens=120,
            included_contexts=len(contexts),
        )

    agent_run = run_research_agent(
        question="Que hace un agente de IA?",
        history=[{"question": "Que es RAG?", "answer": "Recuperacion y generacion."}],
        limit=2,
        search_tool=fake_search_tool,
        answer_tool=fake_answer_tool,
    )

    assert calls["limit"] == 2
    assert "Que es RAG?" in calls["question"]
    assert agent_run.answer == "Un agente piensa, busca y decide con herramientas."
    assert agent_run.sources == fake_results
    assert [step.name for step in agent_run.steps] == [
        "pensar",
        "decidir",
        "buscar",
        "evaluar_contexto",
        "responder",
        "verificar_citas",
    ]
    assert agent_run.steps[2].tool == "search_similar_chunks"
    assert agent_run.steps[3].name == "evaluar_contexto"
    assert agent_run.included_contexts == 1


def test_research_agent_skips_search_for_greeting():
    def failing_search_tool(question: str, limit: int):
        raise AssertionError("Greeting should not trigger document search")

    agent_run = run_research_agent(
        question="hola",
        search_tool=failing_search_tool,
    )

    assert agent_run.used_llm is False
    assert agent_run.sources == []
    assert agent_run.steps[-1].decision == "sin_fuentes_requeridas"


def test_research_agent_generates_local_answer_without_name_error():
    fake_results = [
        SearchResult(
            text="El documento indica que RAG combina busqueda semantica y generacion.",
            filename="rag.pdf",
            page_number=1,
            document_id="doc-rag",
            distance=0.1,
        )
    ]

    agent_run = run_research_agent(
        question="Que dice el documento sobre RAG?",
        search_tool=lambda question, limit: fake_results,
    )

    assert agent_run.used_llm is False
    assert "RAG" in agent_run.answer
    assert agent_run.sources == fake_results
    assert agent_run.included_contexts == 1


def test_research_agent_falls_back_when_groq_fails(monkeypatch):
    import app.llm as llm

    class FailingGroq:
        def __init__(self, api_key: str):
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            raise RuntimeError("groq unavailable")

    fake_results = [
        SearchResult(
            text="El documento habla sobre reglas de idiomas.",
            filename="idiomas.pdf",
            page_number=1,
            document_id="doc-idiomas",
            distance=0.1,
        )
    ]
    monkeypatch.setattr(llm, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm, "Groq", FailingGroq)

    agent_run = run_research_agent(
        question="Sobre que trata el documento?",
        search_tool=lambda question, limit: fake_results,
    )

    assert agent_run.used_llm is False
    assert agent_run.model == "local-context-fallback"
    assert "No se pudo contactar el modelo" in agent_run.answer
    assert agent_run.sources == fake_results
