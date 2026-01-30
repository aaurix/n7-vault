#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepare hourly market data (no LLM summarization).

Goal:
- Run deterministic collection + enrichment.
- Output a JSON object to stdout that an agent can summarize.

This avoids OpenAI chat/completions calls. Embeddings may still be used elsewhere,
but this script does not call hourly.llm_openai.chat_json.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict

from hourly.market_summary_pipeline import (
    PipelineContext,
    build_context,
    spawn_meme_radar,
    fetch_tg_messages,
    build_human_texts,
    build_oi,
    build_viewpoint_threads,
    build_tg_topics,
    wait_meme_radar,
    merge_tg_addr_candidates_into_radar,
)


def run_prepare(total_budget_s: float = 240.0) -> Dict[str, Any]:
    ctx: PipelineContext = build_context(total_budget_s=total_budget_s)

    # Force-disable LLM summarization in this prepare stage.
    ctx.use_llm = False

    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")

    meme_proc = spawn_meme_radar(ctx)

    fetch_tg_messages(ctx)
    build_human_texts(ctx)
    build_oi(ctx)
    build_viewpoint_threads(ctx)
    build_tg_topics(ctx)

    # meme radar join
    wait_meme_radar(ctx, meme_proc)
    merge_tg_addr_candidates_into_radar(ctx)

    # Build twitter evidence packs for the agent (one token per pack)
    ca_inputs = []
    seen = set()
    for it in (ctx.radar_items or [])[:25]:
        dex = (it.get("dex") or {})
        sym = str(dex.get("baseSymbol") or "").upper().strip()
        ca = str(it.get("addr") or "").strip()
        ev = it.get("twitter_evidence") or {}
        snippets = (ev.get("snippets") or [])[:6]
        if not sym or not snippets:
            continue
        key = f"{sym}|{ca[:12]}" if ca else f"{sym}|-"
        if key in seen:
            continue
        seen.add(key)
        pack = {"sym": sym, "evidence": {"snippets": snippets}}
        if ca:
            pack["ca"] = ca
        ca_inputs.append(pack)
        if len(ca_inputs) >= 8:
            break

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "use_llm": False,
        "perf": ctx.perf,
        "errors": ctx.errors,
        "prepared": {
            "oi_lines": ctx.oi_lines,
            "oi_plans": ctx.oi_plans,
            "tg_topics": ctx.narratives,
            "threads_strong": ctx.strong_threads,
            "threads_weak": ctx.weak_threads,
            "radar_items": ctx.radar_items[:15],
            "twitter_ca_inputs": ca_inputs,
        },
    }


def main() -> int:
    budget = float(os.environ.get("HOURLY_MARKET_SUMMARY_BUDGET_S") or 240)
    out = run_prepare(total_budget_s=budget)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
