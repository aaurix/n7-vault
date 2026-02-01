#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Token thread summaries (LLM optional)."""

from __future__ import annotations

from typing import Dict, List

from ..llm_openai import summarize_token_threads_batch
from ..models import PipelineContext
from .pipeline_timing import measure


def build_token_thread_summaries(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "token_thread_llm")

    strong = ctx.strong_threads or []
    weak = ctx.weak_threads or []

    token_threads = (strong[:3] if strong else weak[:3])

    llm_threads: List[Dict[str, str]] = []

    actionable_mode = bool(
        ctx.tg_actionables_attempted
        or (ctx.narratives and any(isinstance(it, dict) and it.get("asset_name") for it in ctx.narratives))
    )
    should_llm = bool(
        ctx.use_llm and token_threads and strong and (not ctx.budget.over(reserve_s=70.0)) and (not actionable_mode)
    )
    if should_llm:
        batch_in: List[Dict[str, object]] = []
        for th in token_threads[:3]:
            sym = str(th.get("sym") or "").upper().strip()
            msgs = th.get("_msgs") or []
            dexm = th.get("_dex") or {}
            metrics = {
                "marketCap": dexm.get("marketCap") or dexm.get("fdv"),
                "vol24h": dexm.get("vol24h"),
                "liquidityUsd": dexm.get("liquidityUsd"),
                "chg1h": dexm.get("chg1h"),
                "chg24h": dexm.get("chg24h"),
                "chainId": dexm.get("chainId"),
                "dexId": dexm.get("dexId"),
            }
            batch_in.append({"token": sym, "metrics": metrics, "telegram": msgs[:20], "twitter": []})

        try:
            bj = summarize_token_threads_batch(items=batch_in)
            outs = bj.get("items") if isinstance(bj, dict) else None
            out_map: Dict[str, Dict[str, str]] = {}
            if isinstance(outs, list):
                for it in outs:
                    if isinstance(it, dict) and it.get("token"):
                        out_map[str(it.get("token") or "").upper()] = it

            for th in token_threads[:3]:
                sym = str(th.get("sym") or "").upper().strip()
                s = out_map.get(sym) or {}
                llm_threads.append(
                    {
                        "title": th.get("title"),
                        "stance": s.get("stance") or th.get("stance"),
                        "count": th.get("count"),
                        "sym": sym,
                        "thesis": s.get("thesis") or "",
                        "drivers": "; ".join(s.get("drivers") or []) if isinstance(s.get("drivers"), list) else (s.get("drivers") or ""),
                        "risks": "; ".join(s.get("risks") or []) if isinstance(s.get("risks"), list) else (s.get("risks") or ""),
                        "trade_implication": s.get("trade_implication") or "",
                        "points": th.get("points") or [],
                    }
                )
        except Exception as e:
            ctx.errors.append(f"llm_token_batch_failed:{e}")

    base_threads = (strong or []) + (weak or [])
    base_threads.sort(key=lambda x: -int(x.get("count") or 0))
    ctx.threads = llm_threads if llm_threads else base_threads

    done()
