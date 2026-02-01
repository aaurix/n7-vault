#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TG热点提炼（事件/叙事）。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..embed_cluster import greedy_cluster
from ..llm_openai import embeddings, summarize_narratives
from ..models import PipelineContext
from ..topic_pipeline import build_topics
from ..tg_topics_fallback import tg_topics_fallback
from .pipeline_timing import measure
from .tg_preprocess import filter_tg_topic_texts, postfilter_tg_topic_item, score_tg_cluster


def build_tg_topics(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "tg_topics_pipeline")

    items: List[Dict[str, Any]] = []
    candidates = filter_tg_topic_texts(ctx.human_texts, resolver=ctx.resolver, limit=240)
    ctx.perf["tg_topics_candidates"] = float(len(candidates))

    if ctx.use_llm and candidates and (not ctx.budget.over(reserve_s=75.0)):
        items = build_topics(
            texts=candidates,
            embeddings_fn=embeddings,
            cluster_fn=greedy_cluster,
            llm_summarizer=summarize_narratives,
            llm_items_key="items",
            prefilter=None,
            postfilter=lambda it: postfilter_tg_topic_item(it, resolver=ctx.resolver),
            cluster_score_fn=lambda it: score_tg_cluster(it, resolver=ctx.resolver),
            max_clusters=12,
            threshold=0.82,
            embed_timeout=26,
            time_budget_ok=lambda reserve: not ctx.budget.over(reserve_s=reserve),
            budget_embed_s=55.0,
            budget_llm_s=70.0,
            errors=ctx.errors,
            tag="tg_topics",
        )

    if not items:
        items = tg_topics_fallback(candidates or ctx.human_texts, limit=5)

    ctx.narratives = items
    done()
