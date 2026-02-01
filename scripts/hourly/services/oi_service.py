#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OI + kline pipeline steps."""

from __future__ import annotations

from typing import Any, Dict, List

from ..config import TG_CHANNELS
from ..kline_fetcher import run_kline_json
from ..llm_openai import summarize_oi_trading_plans
from ..models import PipelineContext
from ..oi import parse_oi_signals
from ..oi_plan_pipeline import build_oi_items, build_oi_plans
from .pipeline_timing import measure


def build_oi(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "oi_items")

    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    oi_signals = parse_oi_signals(ctx.messages_by_chat.get(formula_id, []))

    # Deterministic flow labels
    for s in oi_signals[:]:
        oi = s.get("oi")
        p1h = s.get("p1h")
        if oi is not None and oi > 0 and (p1h or 0) > 0:
            s["flow"] = "增仓跟涨"
        elif oi is not None and oi > 0:
            s["flow"] = "增仓但走弱"
        elif oi is not None and oi < 0 and (p1h or 0) > 0:
            s["flow"] = "减仓上涨"
        else:
            s["flow"] = "减仓/回撤"

    ctx.oi_items = build_oi_items(oi_signals=oi_signals, kline_fetcher=run_kline_json, top_n=5)

    def _fmt_pct(x: Any) -> str:
        return "?" if x is None else f"{float(x):+.1f}%"

    def _fmt_num(x: Any) -> str:
        if x is None:
            return "?"
        try:
            return f"{float(x):.4g}"
        except Exception:
            return str(x)

    lines: List[str] = []
    for it in ctx.oi_items[:5]:
        sym = it.get("symbol")
        px_now = it.get("price_now")
        oi24 = it.get("oi_24h")
        px24 = it.get("price_24h")
        lines.append(f"- {sym} 现价{_fmt_num(px_now)}；24h价{_fmt_pct(px24)}；24h OI{_fmt_pct(oi24)}")

    ctx.oi_lines = lines
    done()


def build_oi_plans_step(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "oi_plans")

    def time_budget_ok(reserve_s: float) -> bool:
        return not ctx.budget.over(reserve_s=reserve_s)

    ctx.oi_plans = build_oi_plans(
        use_llm=ctx.use_llm,
        oi_items=ctx.oi_items,
        llm_fn=summarize_oi_trading_plans,
        time_budget_ok=time_budget_ok,
        budget_s=45.0,
        top_n=3,
        errors=ctx.errors,
        tag="oi_plan",
    )

    done()
