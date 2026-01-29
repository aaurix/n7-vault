#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""On-demand single-symbol analysis (chat runner).

Goal: when user asks "analyze PUMPUSDT" in chat, provide a compact, usable output
without depending on the hourly OI-signal window.

- Uses the same core modules as the hourly pipeline.
- Best-effort and stability-first.
- 1 LLM call max (trader plan); if missing API key or failure, prints rule-based output.

Usage:
  python3 scripts/analyze_symbol.py PUMPUSDT
  python3 scripts/analyze_symbol.py PUMPUSDT --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# make ./scripts importable
sys.path.insert(0, os.path.dirname(__file__))

from hourly.binance_futures import oi_changes, price_changes
from hourly.coingecko import get_market_cap_fdv
from hourly.kline_fetcher import run_kline_json
from hourly.llm_openai import load_openai_api_key, summarize_oi_trading_plans
from hourly.twitter_context import twitter_context_for_symbol


def _fmt_pct(x: Optional[float]) -> str:
    return "?" if x is None else f"{x:+.1f}%"


def _fmt_num(x: Optional[float]) -> str:
    if x is None:
        return "?"
    try:
        return f"{float(x):.4g}"
    except Exception:
        return str(x)


def _fmt_usd(x: Optional[float]) -> str:
    if x is None:
        return "?"
    try:
        x = float(x)
        if x >= 1e9:
            return f"${x/1e9:.2f}B"
        if x >= 1e6:
            return f"${x/1e6:.2f}M"
        if x >= 1e3:
            return f"${x/1e3:.1f}K"
        return f"${x:.0f}"
    except Exception:
        return "?"


def build_item(symbol: str) -> Dict[str, Any]:
    sym = symbol.upper().strip()
    px = price_changes(sym)
    oi = oi_changes(sym)

    k1 = run_kline_json(sym, interval="1h", lookback=120)
    k4 = run_kline_json(sym, interval="4h", lookback=80)

    base = sym.replace("USDT", "")
    mcfdv = get_market_cap_fdv(base)

    tw = twitter_context_for_symbol(sym, limit=8)

    item: Dict[str, Any] = {
        "symbol": sym,
        "price_now": px.get("px_now"),
        "price_1h": px.get("px_1h"),
        "price_4h": px.get("px_4h"),
        "price_24h": px.get("px_24h"),
        "vol_1h": px.get("vol_1h"),
        "oi_now": oi.get("oi_now"),
        "oi_1h": oi.get("oi_1h"),
        "oi_4h": oi.get("oi_4h"),
        "oi_24h": oi.get("oi_24h"),
        "oi_value_now": oi.get("oi_value_now"),
        "oi_value_24h": oi.get("oi_value_24h"),
        "market_cap": mcfdv.get("market_cap"),
        "fdv": mcfdv.get("fdv"),
        "kline_1h": k1,
        "kline_4h": k4,
        "twitter": tw,
    }
    return item


def rule_based_plan(sym: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback plan when LLM is not available."""

    k1 = item.get("kline_1h") if isinstance(item.get("kline_1h"), dict) else {}
    k4 = item.get("kline_4h") if isinstance(item.get("kline_4h"), dict) else {}

    # best-effort: use suggested range levels if present
    rng1 = (k1.get("range") or {}) if isinstance(k1, dict) else {}
    rng4 = (k4.get("range") or {}) if isinstance(k4, dict) else {}

    hi = rng1.get("high") or rng4.get("high")
    lo = rng1.get("low") or rng4.get("low")

    triggers: List[str] = []
    targets: List[str] = []

    if hi is not None:
        triggers.append(f"向上突破 {hi:.6g} 再考虑跟随")
        targets.append(f"上方先看前高/区间上沿 {hi:.6g}")
    if lo is not None:
        triggers.append(f"跌破 {lo:.6g} 再考虑顺势")
        targets.append(f"下方先看区间下沿 {lo:.6g}")

    inv = ""
    if lo is not None:
        inv = f"若跌破 {lo:.6g} 且无法快速收回，则多头思路失效"

    return {
        "symbol": sym,
        "bias": "观望",
        "setup": "数据不足以给出确定方向，建议等待结构确认（突破/跌破）。",
        "triggers": triggers,
        "targets": targets,
        "invalidation": inv,
        "risk_notes": ["仅为规则降级输出；建议结合量能与结构确认。"],
    }


def render_text(item: Dict[str, Any], plan: Optional[Dict[str, Any]]) -> str:
    sym = item.get("symbol") or ""
    px_now = item.get("price_now")
    px24 = item.get("price_24h")
    oi24 = item.get("oi_24h")
    oiv_now = item.get("oi_value_now")

    parts = [
        f"*{sym} 单币分析*",
        f"- 现价：{_fmt_num(px_now)}",
        f"- 24h价格：{_fmt_pct(px24)}",
        f"- 24h OI：{_fmt_pct(oi24)}",
        f"- OI价值：{_fmt_usd(oiv_now)}",
    ]

    mc = item.get("market_cap")
    fdv = item.get("fdv")
    if mc is not None or fdv is not None:
        mcfdv = []
        if mc is not None:
            mcfdv.append(f"MC{_fmt_usd(mc)}")
        if fdv is not None:
            mcfdv.append(f"FDV{_fmt_usd(fdv)}")
        if mcfdv:
            parts.append(f"- {'/'.join(mcfdv)}")

    if plan:
        parts.append("*交易员计划*")
        parts.append(f"- 倾向：{plan.get('bias') or '观望'}")
        setup = (plan.get("setup") or "").strip()
        if setup:
            parts.append(f"- 结构：{setup}")
        triggers = plan.get("triggers") or []
        if isinstance(triggers, list) and triggers:
            parts.append("- 触发：" + "；".join(str(x) for x in triggers[:3] if x))
        targets = plan.get("targets") or []
        if isinstance(targets, list) and targets:
            parts.append("- 目标：" + "；".join(str(x) for x in targets[:3] if x))
        inv = (plan.get("invalidation") or "").strip()
        if inv:
            parts.append(f"- 无效：{inv}")
        rn = plan.get("risk_notes") or []
        if isinstance(rn, list) and rn:
            parts.append("- 风险：" + "；".join(str(x) for x in rn[:3] if x))

    return "\n".join(parts).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="e.g. PUMPUSDT")
    ap.add_argument("--json", action="store_true", help="print json")
    args = ap.parse_args()

    item = build_item(args.symbol)

    plan: Optional[Dict[str, Any]] = None
    # one LLM call max
    if load_openai_api_key():
        try:
            pj = summarize_oi_trading_plans(items=[item])
            its = pj.get("items") if isinstance(pj, dict) else None
            if isinstance(its, list) and its and isinstance(its[0], dict):
                plan = its[0]
        except Exception:
            plan = None

    if plan is None:
        plan = rule_based_plan(item.get("symbol") or args.symbol.upper(), item)

    out = {"item": item, "plan": plan}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(render_text(item, plan))


if __name__ == "__main__":
    main()
