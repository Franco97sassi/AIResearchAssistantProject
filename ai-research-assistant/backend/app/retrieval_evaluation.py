from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class RetrievalMetrics:
    queries: int
    hit_rate_at_k: float
    precision_at_k: float
    recall_at_k: float
    mrr_at_k: float
    ndcg_at_k: float


def evaluate_rankings(
    rankings: list[list[str]], relevant: list[set[str]], k: int
) -> RetrievalMetrics:
    """Compute standard binary-relevance retrieval metrics at k."""
    if len(rankings) != len(relevant):
        raise ValueError("rankings y relevant deben tener la misma longitud")
    hits = precision = recall = reciprocal_rank = ndcg = 0.0
    for ranked, expected in zip(rankings, relevant, strict=True):
        top = ranked[:k]
        found = [item in expected for item in top]
        count = sum(found)
        hits += float(count > 0)
        precision += count / k
        recall += count / max(1, len(expected))
        first = next((index + 1 for index, value in enumerate(found) if value), None)
        reciprocal_rank += 1 / first if first else 0
        dcg = sum(1 / math.log2(index + 2) for index, value in enumerate(found) if value)
        ideal = sum(1 / math.log2(index + 2) for index in range(min(len(expected), k)))
        ndcg += dcg / ideal if ideal else 0
    size = max(1, len(rankings))
    return RetrievalMetrics(
        queries=len(rankings),
        hit_rate_at_k=round(hits / size, 4),
        precision_at_k=round(precision / size, 4),
        recall_at_k=round(recall / size, 4),
        mrr_at_k=round(reciprocal_rank / size, 4),
        ndcg_at_k=round(ndcg / size, 4),
    )


def _chunks(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    step = max(1, size - overlap)
    return [" ".join(words[start : start + size]) for start in range(0, len(words), step)]


def run_experiment(
    rows: list[dict], *, embedding: str, chunk_size: int, overlap: int, rerank: bool, k: int
) -> dict:
    corpus: list[str] = []
    ids: list[str] = []
    for row in rows:
        for index, chunk in enumerate(_chunks(row["text"], chunk_size, overlap)):
            corpus.append(chunk)
            ids.append(f"{row['document_id']}:{index}")
    queries = [row["question"] for row in rows]
    if embedding == "tfidf":
        vectorizer = TfidfVectorizer(ngram_range=(1, 2))
        document_vectors = vectorizer.fit_transform(corpus)
        query_vectors = vectorizer.transform(queries)
    elif embedding == "hashing":
        vectorizer = HashingVectorizer(n_features=384, alternate_sign=False, ngram_range=(1, 2))
        document_vectors = vectorizer.transform(corpus)
        query_vectors = vectorizer.transform(queries)
    else:
        raise ValueError(f"Embedding no soportado: {embedding}")
    similarities = cosine_similarity(query_vectors, document_vectors)
    rankings: list[list[str]] = []
    for query, scores in zip(queries, similarities, strict=True):
        candidates = scores.argsort()[::-1][: max(k, k * 3 if rerank else k)]
        if rerank:
            lexical = TfidfVectorizer(ngram_range=(1, 2)).fit_transform(
                [query, *[corpus[index] for index in candidates]]
            )
            rerank_scores = cosine_similarity(lexical[0:1], lexical[1:]).ravel()
            candidates = candidates[rerank_scores.argsort()[::-1]]
        rankings.append([ids[index].split(":", 1)[0] for index in candidates[:k]])
    metrics = evaluate_rankings(rankings, [{row["relevant_document_id"]} for row in rows], k)
    return {
        "configuration": {
            "embedding": embedding,
            "chunk_size_words": chunk_size,
            "overlap_words": overlap,
            "rerank": rerank,
            "k": k,
        },
        "metrics": asdict(metrics),
    }


def load_dataset(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara configuraciones de retrieval.")
    parser.add_argument("--dataset", type=Path, default=Path("evaluation/retrieval_dataset.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results.json"))
    parser.add_argument("--k", type=int, default=3)
    args = parser.parse_args()
    rows = load_dataset(args.dataset)
    results = [
        run_experiment(
            rows, embedding=embedding, chunk_size=size, overlap=size // 5, rerank=rerank, k=args.k
        )
        for embedding in ("hashing", "tfidf")
        for size in (40, 80)
        for rerank in (False, True)
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
