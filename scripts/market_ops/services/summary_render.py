#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendering step for the hourly summary output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..models import PipelineContext
from ..perp_dashboard import build_perp_dash_inputs
from ..render import WHATSAPP_CHUNK_MAX, build_summary, split_whatsapp_text
from .diagnostics import measure
from .diagnostics import sha1_text


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


def render(ctx: PipelineContext) -> Dict[str, Any]:
    done = measure(ctx.perf, "render")

    title = f"{ctx.now_sh.strftime('%H')}:00 二级山寨+链上meme"

    perp_dash_inputs: List[Dict[str, Any]] = []
    try:
        perp_dash_inputs = build_perp_dash_inputs(oi_items=ctx.oi_items, max_n=3)
    except Exception as e:
        ctx.errors.append(f"perp_dash_inputs_failed:{type(e).__name__}:{e}")
        perp_dash_inputs = []

    summary_whatsapp = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        social_cards=ctx.social_cards,
        twitter_following_summary=ctx.twitter_following_summary,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        perp_dash_inputs=perp_dash_inputs,
        whatsapp=True,
        show_twitter_metrics=False,
    )

    summary_markdown = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        social_cards=ctx.social_cards,
        twitter_following_summary=ctx.twitter_following_summary,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        perp_dash_inputs=perp_dash_inputs,
        whatsapp=False,
        show_twitter_metrics=True,
    )

    tmp_md_path: str = ""
    try:
        tmp = Path("/tmp/clawdbot_hourly_summary.md")
        tmp.write_text(summary_markdown, encoding="utf-8")
        tmp_md_path = str(tmp)
    except Exception as e:
        ctx.errors.append(f"render_markdown_write_failed:{type(e).__name__}:{e}")
        tmp_md_path = ""

    summary_hash = sha1_text(summary_whatsapp + "\n---\n" + summary_markdown)
    summary_whatsapp_chunks = split_whatsapp_text(summary_whatsapp, max_chars=WHATSAPP_CHUNK_MAX)
    metrics_report = build_metrics_report(ctx)

    done()

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "summaryHash": summary_hash,
        "summary_whatsapp": summary_whatsapp,
        "summary_whatsapp_chunks": summary_whatsapp_chunks,
        "summary_markdown": summary_markdown,
        "summary_markdown_path": tmp_md_path,
        "errors": ctx.errors,
        "llm_failures": ctx.llm_failures,
        "metrics_report": metrics_report,
        "elapsed_s": round(ctx.budget.elapsed_s(), 2),
        "perf": ctx.perf,
        "use_llm": bool(ctx.use_llm),
    }
