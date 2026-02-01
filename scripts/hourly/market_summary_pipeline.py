#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Hourly market summary pipeline (orchestrator)."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, Optional

from .config import DEFAULT_TOTAL_BUDGET_S
from .models import PipelineContext
from .services.actionable_normalization import self_check_actionables
from .services.context_builder import build_context
from .services.meme_radar import merge_tg_addr_candidates_into_radar, spawn_meme_radar, wait_meme_radar
from .services.narrative_assets import infer_narrative_assets_from_tg
from .services.oi_service import build_oi, build_oi_plans_step
from .services.sentiment_watch import compute_sentiment_and_watch
from .services.summary_render import render
from .services.telegram_service import build_human_texts, build_viewpoint_threads, fetch_tg_messages, require_tg_health
from .services.tg_topics import build_tg_topics
from .services.token_threads import build_token_thread_summaries
from .services.twitter_topics import build_twitter_ca_topics


def run_pipeline(*, total_budget_s: float = DEFAULT_TOTAL_BUDGET_S) -> Dict[str, Any]:
    ctx = build_context(total_budget_s=total_budget_s)

    meme_proc: Optional[subprocess.Popen[str]] = None
    try:
        require_tg_health(ctx)

        meme_proc = spawn_meme_radar(ctx)

        fetch_tg_messages(ctx)
        build_human_texts(ctx)
        build_oi(ctx)
        build_oi_plans_step(ctx)
        build_viewpoint_threads(ctx)
        build_tg_topics(ctx)

        wait_meme_radar(ctx, meme_proc)
        merge_tg_addr_candidates_into_radar(ctx)
        build_twitter_ca_topics(ctx)

        build_token_thread_summaries(ctx)
        infer_narrative_assets_from_tg(ctx)
        compute_sentiment_and_watch(ctx)

        return render(ctx)
    except Exception as e:
        # Ensure valid JSON even on fatal errors.
        try:
            if meme_proc is not None:
                meme_proc.kill()
        except Exception:
            pass

        ctx.errors.append(f"fatal:{type(e).__name__}:{e}")
        # Try to render something minimal; if render also fails, return a minimal object.
        try:
            if not ctx.sentiment:
                ctx.sentiment = "分歧"
            return render(ctx)
        except Exception as e2:
            return {
                "since": ctx.since,
                "until": ctx.until,
                "hourKey": ctx.hour_key,
                "summaryHash": "",
                "summary_whatsapp": "",
                "summary_whatsapp_chunks": [],
                "summary_markdown": "",
                "summary_markdown_path": "",
                "errors": ctx.errors + [f"fatal_render:{type(e2).__name__}:{e2}"],
                "llm_failures": ctx.llm_failures,
                "elapsed_s": round(ctx.budget.elapsed_s(), 2),
                "perf": ctx.perf,
                "use_llm": bool(ctx.use_llm),
            }
