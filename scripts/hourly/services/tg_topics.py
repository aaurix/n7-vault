#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TG热点/可交易标的提炼。"""

from __future__ import annotations

from typing import Any, Dict, List

from ..llm_openai import summarize_tg_actionables
from ..models import PipelineContext
from .actionable_normalization import _fallback_actionables_from_texts, _normalize_actionables
from .llm_failures import _log_llm_failure
from .pipeline_timing import measure
from .snippet_prep import _prep_tg_snippets


def build_tg_topics(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "tg_topics_pipeline")

    items: List[Dict[str, Any]] = []
    snippets = _prep_tg_snippets(ctx.human_texts, limit=120)
    ctx.perf["tg_snippets"] = float(len(snippets))

    if ctx.use_llm and snippets and (not ctx.budget.over(reserve_s=70.0)):
        ctx.tg_actionables_attempted = True
        try:
            out = summarize_tg_actionables(tg_snippets=snippets)
            raw_items = out.get("items") if isinstance(out, dict) else None
            parse_failed = bool(isinstance(out, dict) and out.get("_parse_failed"))
            raw = str(out.get("raw") or "") if isinstance(out, dict) else ""
            if parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_parse_failed", raw=raw)
            if isinstance(raw_items, list):
                items = _normalize_actionables(raw_items)
            elif isinstance(out, dict) and not parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_schema_invalid", raw=raw)
            if not items and not parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_empty", raw=raw)
        except Exception as e:
            _log_llm_failure(ctx, "tg_actionables_llm_failed", exc=e)

    if not items:
        items = _fallback_actionables_from_texts(ctx.human_texts, limit=5)

    ctx.narratives = items
    done()
