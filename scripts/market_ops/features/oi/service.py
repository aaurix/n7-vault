#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OI/Price signal parsing + plan pipeline."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ...config import TG_CHANNELS
from ...kline_fetcher import run_kline_json
from ...llm_openai import summarize_oi_trading_plans
from ...models import PipelineContext
from ...services.diagnostics import measure
from .plan import build_oi_items, build_oi_plans


_TICKER_EXCLUDE = {"BTC", "ETH", "SOL", "BNB", "BSC", "BASE", "USDT", "USDC", "USD", "FDV", "MCAP", "DEX", "GMGN", "OI", "CA"}


def parse_oi_signals(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract {symbol, dir, oi, p1h, p24h} from messages.

    Supports both:
    - "OI +12.3%"
    - "openinterest +12.3%"
    - "未平仓合约增加12.3%"
    """

    out: List[Dict[str, Any]] = []

    sym_re = re.compile(r"\b([A-Z0-9]{2,12})\b")
    oi_re = re.compile(r"(?:OI|openinterest|未平仓合约)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%", re.IGNORECASE)
    h1_re = re.compile(r"(?:3600秒|1h|1H|1小时|1小時)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%")
    h24_re = re.compile(r"(?:24h|24H|24小时|24小時)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%")

    for m in messages:
        t = (m.get("raw_text") or m.get("text") or "").strip()
        if not t:
            continue
        oi_m = oi_re.search(t)
        if not oi_m:
            continue
        oi = float(oi_m.group(1))

        h1_m = h1_re.search(t)
        h24_m = h24_re.search(t)
        p1h = float(h1_m.group(1)) if h1_m else None
        p24h = float(h24_m.group(1)) if h24_m else None

        sym = None
        head = t[:100]
        for cand in sym_re.findall(head):
            if cand in _TICKER_EXCLUDE:
                continue
            if cand.isdigit():
                continue
            sym = cand
            break
        if not sym:
            continue

        direction = "↑" if (p1h is not None and p1h > 0) or (oi > 0) else "↓"
        out.append({"symbol": sym, "dir": direction, "oi": oi, "p1h": p1h, "p24h": p24h, "raw": t[:220]})

    # rank
    def score(x):
        return (abs(x.get("oi") or 0), abs(x.get("p1h") or 0))

    out.sort(key=score, reverse=True)

    seen = set()
    uniq = []
    for it in out:
        if it["symbol"] in seen:
            continue
        seen.add(it["symbol"])
        uniq.append(it)
    return uniq[:8]


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
