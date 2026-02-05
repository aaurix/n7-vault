from __future__ import annotations

from typing import Any, Dict, List

from market_ops.topic_pipeline import build_topics


def test_build_topics_dedup_and_cluster_flow() -> None:
    texts = [" Alpha ", "alpha", "Beta", "", "Beta"]
    calls: Dict[str, Any] = {}

    def embeddings_fn(*, texts: List[str], timeout: int) -> List[List[float]]:
        calls["embeddings"] = texts
        return [[0.1] for _ in texts]

    def cluster_fn(items: List[Dict[str, Any]], vecs: List[List[float]], *, max_clusters: int, threshold: float) -> List[Dict[str, Any]]:
        calls["cluster"] = {"items": items, "vecs": vecs, "max": max_clusters, "threshold": threshold}
        return [
            {"text": items[1]["text"], "_cluster_size": 2},
            {"text": items[0]["text"], "_cluster_size": 1},
        ]

    def llm_summarizer(**kwargs: Any) -> Dict[str, Any]:
        calls["llm"] = kwargs
        return {"items": [{"one_liner": "Beta narrative"}]}

    errors: List[str] = []
    out = build_topics(
        texts=texts,
        embeddings_fn=embeddings_fn,
        cluster_fn=cluster_fn,
        llm_summarizer=llm_summarizer,
        llm_items_key="items",
        max_clusters=4,
        threshold=0.8,
        embed_timeout=5,
        time_budget_ok=lambda _reserve: True,
        errors=errors,
        tag="topic",
    )

    assert "embeddings" not in calls
    assert calls["llm"]["tg_messages"] == ["Alpha", "Beta"]
    assert out == [{"one_liner": "Beta narrative"}]
    assert errors == []


def test_build_topics_budget_skip_embed() -> None:
    texts = ["Alpha unlock", "Beta listing"]
    calls: Dict[str, Any] = {}

    def embeddings_fn(*, texts: List[str], timeout: int) -> List[List[float]]:
        calls["embeddings"] = True
        return [[0.1] for _ in texts]

    def cluster_fn(items: List[Dict[str, Any]], vecs: List[List[float]], *, max_clusters: int, threshold: float) -> List[Dict[str, Any]]:
        calls["cluster"] = True
        return items

    def llm_summarizer(**kwargs: Any) -> Dict[str, Any]:
        calls["llm"] = kwargs
        return {"items": [{"one_liner": "Alpha"}]}

    errors: List[str] = []

    def time_budget_ok(reserve: float) -> bool:
        return reserve > 60  # skip embed (55), allow llm (65)

    out = build_topics(
        texts=texts,
        embeddings_fn=embeddings_fn,
        cluster_fn=cluster_fn,
        llm_summarizer=llm_summarizer,
        llm_items_key="items",
        time_budget_ok=time_budget_ok,
        errors=errors,
        tag="topic",
    )

    assert "topic_embed_skipped:budget" in errors
    assert calls["llm"]["tg_messages"] == ["Alpha unlock", "Beta listing"]
    assert out == [{"one_liner": "Alpha"}]
