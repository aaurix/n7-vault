#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rendering step for the hourly summary output."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..models import PipelineContext
from ..perp_dashboard import build_perp_dash_inputs
from ..render import build_summary, split_whatsapp_text
from .pipeline_timing import measure
from .text_hash import sha1_text


def render(ctx: PipelineContext) -> Dict[str, Any]:
    done = measure(ctx.perf, "render")

    title = f"{ctx.now_sh.strftime('%H')}:00 二级山寨+链上meme"

    perp_dash_inputs: List[Dict[str, Any]] = []
    try:
        perp_dash_inputs = build_perp_dash_inputs(oi_items=ctx.oi_items, max_n=3)
    except Exception:
        perp_dash_inputs = []

    summary_whatsapp = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        social_cards=ctx.social_cards,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        perp_dash_inputs=perp_dash_inputs,
        whatsapp=True,
    )

    summary_markdown = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        social_cards=ctx.social_cards,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        perp_dash_inputs=perp_dash_inputs,
        whatsapp=False,
    )

    tmp_md_path: str = ""
    try:
        tmp = Path("/tmp/clawdbot_hourly_summary.md")
        tmp.write_text(summary_markdown, encoding="utf-8")
        tmp_md_path = str(tmp)
    except Exception:
        tmp_md_path = ""

    summary_hash = sha1_text(summary_whatsapp + "\n---\n" + summary_markdown)
    summary_whatsapp_chunks = split_whatsapp_text(summary_whatsapp, max_chars=950)

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
        "elapsed_s": round(ctx.budget.elapsed_s(), 2),
        "perf": ctx.perf,
        "use_llm": bool(ctx.use_llm),
    }
