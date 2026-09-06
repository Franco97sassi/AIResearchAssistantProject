from app.retrieval_evaluation import evaluate_rankings, run_experiment


def test_retrieval_metrics_known_ranking():
    metrics = evaluate_rankings([["a", "b"], ["x", "c"]], [{"a"}, {"c"}], 2)
    assert metrics.hit_rate_at_k == 1.0
    assert metrics.precision_at_k == 0.5
    assert metrics.recall_at_k == 1.0
    assert metrics.mrr_at_k == 0.75


def test_experiment_reports_configuration_and_metrics():
    rows = [
        {
            "question": "vector retrieval",
            "document_id": "doc",
            "relevant_document_id": "doc",
            "text": "vector retrieval finds evidence",
        }
    ]
    result = run_experiment(rows, embedding="hashing", chunk_size=20, overlap=2, rerank=True, k=1)
    assert result["configuration"]["rerank"] is True
    assert result["metrics"]["recall_at_k"] == 1.0
