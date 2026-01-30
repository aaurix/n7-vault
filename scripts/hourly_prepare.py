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
from typing import Any, Dict, List, Tuple

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
from hourly.filters import extract_symbols_and_addrs, stance_from_texts


def _tg_topics_fallback(texts: List[str], *, limit: int = 5) -> List[Dict[str, Any]]:
    """Deterministic TG topic extraction fallback (no embeddings/LLM).

    We cluster loosely by mentioned tickers/addresses. This is intentionally simple
    but ensures we don't emit an empty topics section when LLM is disabled.
    """

    sym_hits: Dict[str, int] = {}
    sym_samples: Dict[str, List[str]] = {}

    for t in texts[:800]:
        syms, _addrs = extract_symbols_and_addrs(t)
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


def run_prepare(total_budget_s: float = 240.0) -> Dict[str, Any]:
    ctx: PipelineContext = build_context(total_budget_s=total_budget_s)

    # Default: enable LLM in prepare stage when available.
    # You can disable via env HOURLY_PREP_USE_LLM=0.
    if os.environ.get("HOURLY_PREP_USE_LLM") in {"0", "false", "False"}:
        ctx.use_llm = False

    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")

    meme_proc = spawn_meme_radar(ctx)

    fetch_tg_messages(ctx)
    build_human_texts(ctx)
    build_oi(ctx)

    # LLM-based OI plans (optional, budgeted)
    if ctx.use_llm:
        from hourly.market_summary_pipeline import build_oi_plans_step

        build_oi_plans_step(ctx)

    build_viewpoint_threads(ctx)
    build_tg_topics(ctx)

    # Deterministic fallback: build_tg_topics() is LLM-gated, so ctx.narratives can be empty.
    if not ctx.narratives:
        ctx.narratives = _tg_topics_fallback(ctx.human_texts, limit=5)

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

    debug = {
        "human_texts": len(ctx.human_texts or []),
        "messages_by_chat": {k: len(v or []) for k, v in (ctx.messages_by_chat or {}).items()},
        "tg_topics_inferred": any(bool(it.get("_inferred")) for it in (ctx.narratives or []) if isinstance(it, dict)),
    }

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "use_llm": bool(ctx.use_llm),
        "perf": ctx.perf,
        "errors": ctx.errors,
        "prepared": {
            "oi_lines": ctx.oi_lines,
            "oi_items": ctx.oi_items,
            "oi_plans": ctx.oi_plans,
            "tg_topics": ctx.narratives,
            "threads_strong": ctx.strong_threads,
            "threads_weak": ctx.weak_threads,
            "radar_items": ctx.radar_items[:15],
            "twitter_ca_inputs": ca_inputs,
            "debug": debug,
        },
    }


def main() -> int:
    budget = float(os.environ.get("HOURLY_MARKET_SUMMARY_BUDGET_S") or 240)
    out = run_prepare(total_budget_s=budget)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
