#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Topic pipeline (production):

prefilter -> dedup -> embeddings cluster (K, optional scoring) -> LLM summarize -> postfilter -> normalize

Used for:
- Telegram 热点
- Twitter 热点

Stability-first:
- caller passes a time budget fn; this pipeline will skip expensive steps when over budget.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def _dedup_texts(texts: List[str], *, key_len: int = 120, limit: int = 200) -> List[str]:
    out: List[str] = []
    seen = set()
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        k = t.lower()[:key_len]
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _rank_texts_by_score(
    texts: List[str],
    *,
    score_fn: Optional[Callable[[Dict[str, Any]], float]],
    limit: int,
) -> List[str]:
    if not texts:
        return []
    if not score_fn:
        return texts[:limit] if limit > 0 else texts
    scored: List[tuple[float, int, str]] = []
    for idx, t in enumerate(texts):
        if not t:
            continue
        try:
            score = float(score_fn({"text": t, "_cluster_size": 1}))
        except Exception:
            score = 0.0
        scored.append((score, idx, t))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _score, _idx, t in scored[:limit]]


def build_topics(
    *,
    texts: List[str],
    embeddings_fn: Callable[..., List[List[float]]],
    cluster_fn: Callable[..., List[Dict[str, Any]]],
    llm_summarizer: Callable[..., Dict[str, Any]],
    llm_items_key: str = "items",
    prefilter: Optional[Callable[[str], bool]] = None,
    postfilter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    cluster_score_fn: Optional[Callable[[Dict[str, Any]], float]] = None,
    max_clusters: int = 10,
    threshold: float = 0.82,
    embed_timeout: int = 30,
    time_budget_ok: Optional[Callable[[float], bool]] = None,
    budget_embed_s: float = 55.0,
    budget_llm_s: float = 65.0,
    # how to pass into llm_summarizer
    llm_arg_name: str = "tg_messages",
    # optional error sink
    errors: Optional[List[str]] = None,
    tag: str = "topic",
) -> List[Dict[str, Any]]:
    """Return normalized topic dict list.

    text list -> representative texts -> llm -> normalize
    """

    time_budget_ok = time_budget_ok or (lambda _limit: True)
    if errors is None:
        errors = []

    # 1) prefilter + dedup
    filtered: List[str] = []
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        if prefilter and not prefilter(t):
            continue
        filtered.append(t)

    filtered = _dedup_texts(filtered, limit=200)

    if not filtered:
        errors.append(f"{tag}_empty")
        return []

    reps_texts = filtered

    def _ranked(limit: int) -> List[str]:
        if not cluster_score_fn:
            return filtered
        return _rank_texts_by_score(filtered, score_fn=cluster_score_fn, limit=limit)

    # 2) embeddings clustering (optional)
    if time_budget_ok(budget_embed_s) and len(filtered) > max_clusters:
        try:
            vecs = embeddings_fn(texts=[t[:240] for t in filtered], timeout=embed_timeout)
            items = [{"text": t} for t in filtered]
            reps = cluster_fn(items, vecs, max_clusters=max_clusters, threshold=threshold)
            if cluster_score_fn:
                for r in reps:
                    if isinstance(r, dict):
                        try:
                            r["_cluster_score"] = float(cluster_score_fn(r))
                        except Exception:
                            pass
                reps = sorted(
                    reps,
                    key=lambda x: (
                        float((x or {}).get("_cluster_score") or 0.0),
                        float((x or {}).get("_cluster_size") or 0.0),
                    ),
                    reverse=True,
                )
            reps_texts = [x.get("text") for x in reps if x.get("text")] or reps_texts
        except Exception as e:
            errors.append(f"{tag}_embed_failed:{e}")
            reps_texts = _ranked(min(len(filtered), max_clusters))
    else:
        if not time_budget_ok(budget_embed_s):
            errors.append(f"{tag}_embed_skipped:budget")
        reps_texts = _ranked(min(len(filtered), max_clusters))

    # 3) llm summarize
    if not time_budget_ok(budget_llm_s):
        errors.append(f"{tag}_llm_skipped:budget")
        return []

    try:
        kwargs = {llm_arg_name: reps_texts}
        out = llm_summarizer(**kwargs)
    except Exception as e:
        errors.append(f"{tag}_llm_failed:{e}")
        return []

    raw_items = out.get(llm_items_key) if isinstance(out, dict) else None
    if not isinstance(raw_items, list):
        errors.append(f"{tag}_llm_bad_output")
        return []

    norm: List[Dict[str, Any]] = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        if postfilter and not postfilter(it):
            continue
        norm.append(it)

    return norm
