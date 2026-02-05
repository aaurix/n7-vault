#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lightweight observability summary for the hourly pipeline."""

from __future__ import annotations

from typing import Any, Dict, List

from ..models import PipelineContext


def _top_steps(perf: Dict[str, float], *, limit: int = 5) -> List[Dict[str, Any]]:
    items = sorted(perf.items(), key=lambda kv: float(kv[1]), reverse=True)
    out: List[Dict[str, Any]] = []
    for name, sec in items[:limit]:
        out.append({"step": name, "seconds": float(sec)})
    return out


def build_metrics_report(ctx: PipelineContext) -> Dict[str, Any]:
    """Return a compact metrics report for debugging/observability."""

    perf = ctx.perf or {}
    report: Dict[str, Any] = {
        "elapsed_s": round(ctx.budget.elapsed_s(), 2),
        "use_llm": bool(ctx.use_llm),
        "use_embeddings": bool(ctx.use_embeddings),
        "errors": len(ctx.errors),
        "llm_failures": len(ctx.llm_failures),
        "tg_topics_fallback": ctx.tg_topics_fallback_reason or "",
        "slow_steps": _top_steps(perf, limit=5),
        "counts": {
            "human_texts": len(ctx.human_texts or []),
            "narratives": len(ctx.narratives or []),
            "threads": len(ctx.threads or []),
            "social_cards": len(ctx.social_cards or []),
        },
    }

    if ctx.errors:
        report["recent_errors"] = ctx.errors[-3:]
    if ctx.llm_failures:
        report["recent_llm_failures"] = ctx.llm_failures[-3:]

    tw_metrics = {}
    if isinstance(ctx.twitter_following, dict):
        tw_metrics = ctx.twitter_following.get("metrics") or {}
    if isinstance(tw_metrics, dict) and tw_metrics:
        report["twitter_following"] = {
            "total": tw_metrics.get("total"),
            "kept": tw_metrics.get("kept"),
            "clusters": tw_metrics.get("clusters"),
            "noise_drop_rate": tw_metrics.get("noise_drop_rate"),
            "dedupe_rate": tw_metrics.get("dedupe_rate"),
            "capped": tw_metrics.get("capped"),
        }

    return report


__all__ = ["build_metrics_report"]
