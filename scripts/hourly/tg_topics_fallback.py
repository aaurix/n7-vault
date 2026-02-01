#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic Telegram topics fallback (no embeddings/LLM)."""

from __future__ import annotations

from typing import Any, Dict, List

from .filters import stance_from_texts
from .services.entity_resolver import get_shared_entity_resolver
from .services.tg_preprocess import filter_tg_topic_texts


def tg_topics_fallback(texts: List[str], *, limit: int = 5) -> List[Dict[str, Any]]:
    """Deterministic TG topic extraction fallback (no embeddings/LLM).

    We cluster loosely by mentioned tickers/addresses after deterministic prefiltering.
    This is intentionally simple but ensures we don't emit an empty topics section when LLM is disabled.
    """

    resolver = get_shared_entity_resolver()
    sym_hits: Dict[str, int] = {}
    sym_samples: Dict[str, List[str]] = {}

    filtered = filter_tg_topic_texts(texts, resolver=resolver, limit=400)

    for t in filtered[:400]:
        syms, _addrs = resolver.extract_symbols_and_addrs(t)
        for s in syms[:3]:
            sym_hits[s] = sym_hits.get(s, 0) + 1
            sym_samples.setdefault(s, []).append(t)

    items: List[Dict[str, Any]] = []
    for sym, cnt in sorted(sym_hits.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]:
        samples = sym_samples.get(sym, [])[:30]
        stance = stance_from_texts(samples)
        one = f"{sym} 讨论升温（提及{cnt}）"
        tri = "关注关键位/催化/风险"  # placeholder without overfitting rules
        items.append(
            {
                "one_liner": one,
                "sentiment": stance,
                "triggers": tri,
                "related_assets": [sym],
                "_inferred": True,
            }
        )

    return items[:limit]
