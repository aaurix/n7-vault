#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Embedding-based clustering (greedy) for compressing noisy message streams.

Design: pick ~K representative items for LLM summarization.
- Fast & simple greedy clustering by cosine similarity.
- Deterministic ordering: process items in given order.

This is used for:
- Twitter: cluster radar snippets into topics before LLM.
- Telegram热点: cluster chat messages into themes before LLM.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: List[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine(a: List[float], b: List[float]) -> float:
    na = _norm(a)
    nb = _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return _dot(a, b) / (na * nb)


def greedy_cluster(
    items: List[Dict[str, Any]],
    vectors: List[List[float]],
    *,
    text_key: str = "text",
    max_clusters: int = 10,
    threshold: float = 0.82,
) -> List[Dict[str, Any]]:
    """Return representative items (one per cluster), plus cluster meta.

    Each output item contains:
    - original fields
    - _cluster_size
    - _cluster_members (optional small sample)
    """

    if not items or not vectors or len(items) != len(vectors):
        return items[:max_clusters]

    clusters: List[Dict[str, Any]] = []
    centroids: List[List[float]] = []

    for it, v in zip(items, vectors):
        # find best cluster
        best_i = -1
        best_sim = -1.0
        for i, c in enumerate(centroids):
            s = cosine(v, c)
            if s > best_sim:
                best_sim = s
                best_i = i

        if best_i >= 0 and best_sim >= threshold:
            cl = clusters[best_i]
            cl["_cluster_size"] = int(cl.get("_cluster_size") or 1) + 1
            # keep a tiny sample of member texts for debugging/context
            mem = cl.get("_cluster_members") or []
            if isinstance(mem, list) and len(mem) < 3:
                mem.append(str(it.get(text_key) or "")[:140])
                cl["_cluster_members"] = mem
            continue

        # create new cluster if room
        if len(clusters) < max_clusters:
            out = dict(it)
            out["_cluster_size"] = 1
            out["_cluster_members"] = [str(it.get(text_key) or "")[:140]]
            clusters.append(out)
            centroids.append(v)
        else:
            # if over limit, ignore; we already have max_clusters representatives
            continue

    return clusters
