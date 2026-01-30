#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Prepare deterministic single-symbol analysis context (no LLM).

This script is the *prepare stage* for on-demand symbol analysis.
It mirrors the hourly_prepare pattern:
- deterministic collection + enrichment
- prints one JSON object to stdout
- NO OpenAI chat/completions calls

Usage:
  python3 scripts/analyze_symbol_prepare.py PUMPUSDT
  python3 scripts/analyze_symbol_prepare.py PUMPUSDT --pretty

Output contract (best-effort):
{
  symbol,
  use_llm: false,
  prepared: {
    price, oi, market,
    kline_1h, kline_4h,
    twitter: {total, kept, kept_ratio, snippets, stats},
    derived: {flow_label, bias_hint, scores, key_levels, labels}
  },
  errors: []
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# make ./scripts importable
sys.path.insert(0, os.path.dirname(__file__))

from hourly.binance_futures import oi_changes, price_changes  # noqa: E402
from hourly.coingecko import get_market_cap_fdv  # noqa: E402
from hourly.kline_fetcher import run_kline_json  # noqa: E402
from hourly.twitter_context import twitter_context_for_symbol  # noqa: E402


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _as_num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_get(d: Any, *keys: str) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _flow_label(*, px_chg: Optional[float], oi_chg: Optional[float]) -> str:
    """Price/OI quadrant label (deterministic heuristic)."""

    if not isinstance(px_chg, (int, float)) or not isinstance(oi_chg, (int, float)):
        return "资金方向不明"

    if oi_chg >= 5 and px_chg >= 1:
        return "多头加仓（价↑OI↑）"
    if oi_chg >= 5 and px_chg <= -1:
        return "空头加仓（价↓OI↑）"
    if oi_chg <= -5 and px_chg >= 1:
        return "空头回补（价↑OI↓）"
    if oi_chg <= -5 and px_chg <= -1:
        return "多头止损/出清（价↓OI↓）"

    return "轻微/震荡（价/OI变化不大）"


def _key_levels(k1: Dict[str, Any], k4: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Return key support/resistance levels (prefer 1h swing, then range, then 4h)."""

    def _pick(d: Dict[str, Any], path: Tuple[str, str]) -> Optional[float]:
        v = _safe_get(d, path[0], path[1])
        return _as_num(v)

    r1 = _pick(k1, ("swing", "hi")) or _pick(k1, ("range", "hi")) or _pick(k4, ("swing", "hi")) or _pick(k4, ("range", "hi"))
    s1 = _pick(k1, ("swing", "lo")) or _pick(k1, ("range", "lo")) or _pick(k4, ("swing", "lo")) or _pick(k4, ("range", "lo"))
    return {"resistance": r1, "support": s1}


def _twitter_stats(snippets: List[str]) -> Dict[str, Any]:
    """Simple deterministic evidence stats (no sentiment model)."""

    bull_terms = [
        "long",
        "buy",
        "bull",
        "breakout",
        "break out",
        "support",
        "bounce",
        "higher",
        "看多",
        "做多",
        "多单",
        "突破",
        "支撑",
        "反弹",
    ]
    bear_terms = [
        "short",
        "sell",
        "bear",
        "rejection",
        "resistance",
        "dump",
        "down",
        "rug",
        "scam",
        "hack",
        "看空",
        "做空",
        "空单",
        "压制",
        "跌破",
        "砸盘",
        "跑路",
        "诈骗",
        "被黑",
    ]
    trader_terms = ["tp", "sl", "stop", "entry", "exit", "support", "resistance", "long", "short", "突破", "止损", "入场", "止盈"]

    bull_hits = 0
    bear_hits = 0
    trader_talk_hits = 0
    lens: List[int] = []

    for s in snippets or []:
        t = (s or "").strip()
        if not t:
            continue
        low = t.lower()
        lens.append(len(t))
        if any(k in low for k in bull_terms):
            bull_hits += 1
        if any(k in low for k in bear_terms):
            bear_hits += 1
        if any(k in low for k in trader_terms):
            trader_talk_hits += 1

    avg_len = round(sum(lens) / len(lens), 1) if lens else 0.0

    # crude: bull - bear in [-1, 1]
    stance_score = 0.0
    if bull_hits or bear_hits:
        stance_score = (bull_hits - bear_hits) / max(1.0, float(bull_hits + bear_hits))
        stance_score = float(_clamp(stance_score, -1.0, 1.0))

    return {
        "snippets": len(snippets or []),
        "avg_len": avg_len,
        "bull_hits": bull_hits,
        "bear_hits": bear_hits,
        "trader_talk_hits": trader_talk_hits,
        "stance_score": round(stance_score, 3),
    }


def _scores(*, k1: Dict[str, Any], k4: Dict[str, Any], px: Dict[str, Any], oi: Dict[str, Any], tw: Dict[str, Any]) -> Dict[str, int]:
    """Deterministic 0-100 scoring for dashboard.

    These scores are *heuristic*; the agent can use them as a baseline.
    """

    slope4 = _as_num(k4.get("ema20_slope_pct"))
    rsi1 = _as_num(k1.get("rsi14"))
    pos1 = _as_num(_safe_get(k1, "range", "pos"))

    px4 = _as_num(px.get("price_4h"))
    oi4 = _as_num(oi.get("oi_4h"))

    # Trend score
    tr = 0.0
    if slope4 is not None:
        tr += _clamp(slope4 / 0.2, -2.0, 2.0)  # slope4 ~ pct
    if rsi1 is not None:
        tr += _clamp((rsi1 - 50.0) / 10.0, -2.0, 2.0)
    if pos1 is not None:
        # near high supports trend continuation but also warns overextension; keep mild.
        tr += _clamp((pos1 - 0.5) * 1.2, -0.6, 0.6)
    trend = int(round(_clamp(50.0 + 12.0 * tr, 0.0, 100.0)))

    # OI/flow score
    fr = 0.0
    if px4 is not None and oi4 is not None:
        # quadrant synergy
        if px4 >= 1 and oi4 >= 5:
            fr += 2.0
        elif px4 <= -1 and oi4 >= 5:
            fr -= 2.0
        elif px4 >= 1 and oi4 <= -5:
            fr += 0.8
        elif px4 <= -1 and oi4 <= -5:
            fr -= 0.8
        fr += _clamp(oi4 / 8.0, -1.5, 1.5)
    else:
        oi1 = _as_num(oi.get("oi_1h"))
        px1 = _as_num(px.get("price_1h"))
        if px1 is not None and oi1 is not None:
            fr += _clamp(oi1 / 6.0, -1.5, 1.5)
    oi_score = int(round(_clamp(50.0 + 14.0 * fr, 0.0, 100.0)))

    # Social score
    kept = int(tw.get("kept") or 0)
    total = int(tw.get("total") or 0)
    ratio = float(tw.get("kept_ratio") or (kept / total if total else 0.0))
    st = tw.get("stats") if isinstance(tw.get("stats"), dict) else {}
    stance = _as_num(st.get("stance_score")) or 0.0
    intensity = _clamp(kept / 6.0, 0.0, 1.0)

    sr = 0.0
    sr += 1.2 * ratio
    sr += 0.8 * intensity
    sr += 0.3 * abs(stance)
    social = int(round(_clamp(25.0 + 55.0 * sr, 0.0, 100.0)))

    overall = int(round(_clamp(0.45 * trend + 0.35 * oi_score + 0.20 * social, 0.0, 100.0)))

    return {"trend": trend, "oi": oi_score, "social": social, "overall": overall}


def run_prepare(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").upper().strip()
    errors: List[str] = []

    px: Dict[str, Any] = {}
    oi: Dict[str, Any] = {}
    k1: Dict[str, Any] = {}
    k4: Dict[str, Any] = {}
    mcfdv: Dict[str, Any] = {}
    tw: Dict[str, Any] = {}

    try:
        px = price_changes(sym)
    except Exception as e:
        errors.append(f"price_changes:{type(e).__name__}:{e}")

    try:
        oi = oi_changes(sym)
    except Exception as e:
        errors.append(f"oi_changes:{type(e).__name__}:{e}")

    try:
        k1 = run_kline_json(sym, interval="1h", lookback=120)
    except Exception as e:
        errors.append(f"kline_1h:{type(e).__name__}:{e}")

    try:
        k4 = run_kline_json(sym, interval="4h", lookback=80)
    except Exception as e:
        errors.append(f"kline_4h:{type(e).__name__}:{e}")

    try:
        base = sym.replace("USDT", "")
        mcfdv = get_market_cap_fdv(base)
    except Exception as e:
        errors.append(f"coingecko:{type(e).__name__}:{e}")

    try:
        tw = twitter_context_for_symbol(sym, limit=8)
    except Exception as e:
        errors.append(f"twitter:{type(e).__name__}:{e}")
        tw = {"total": 0, "kept": 0, "snippets": []}

    snippets = (tw.get("snippets") or []) if isinstance(tw.get("snippets"), list) else []
    snippets = [str(x) for x in snippets if isinstance(x, str) and x.strip()][:8]

    tw_out = {
        "total": int(tw.get("total") or 0),
        "kept": int(tw.get("kept") or 0),
        "kept_ratio": round((int(tw.get("kept") or 0) / int(tw.get("total") or 1)), 3) if int(tw.get("total") or 0) else 0.0,
        "snippets": snippets,
        "stats": _twitter_stats(snippets),
    }

    # flow label: prefer 4h
    flow = _flow_label(px_chg=_as_num(px.get("px_4h")) or _as_num(px.get("px_1h")), oi_chg=_as_num(oi.get("oi_4h")) or _as_num(oi.get("oi_1h")))

    levels = _key_levels(k1 if isinstance(k1, dict) else {}, k4 if isinstance(k4, dict) else {})

    scores = _scores(k1=k1 if isinstance(k1, dict) else {}, k4=k4 if isinstance(k4, dict) else {}, px={
        "price_1h": px.get("px_1h"),
        "price_4h": px.get("px_4h"),
    }, oi={"oi_1h": oi.get("oi_1h"), "oi_4h": oi.get("oi_4h")}, tw=tw_out)

    bias_hint = "观望"
    if scores["trend"] >= 62 and scores["oi"] >= 58:
        bias_hint = "偏多"
    elif scores["trend"] <= 38 and scores["oi"] <= 42:
        bias_hint = "偏空"

    atr14 = _as_num(k1.get("atr14"))
    last = _as_num(k1.get("last"))
    atr_pct = round((atr14 / last) * 100.0, 2) if (atr14 and last) else None

    derived = {
        "flow_label": flow,
        "bias_hint": bias_hint,
        "scores": scores,
        "key_levels": levels,
        "labels": {
            "range_loc_1h": _safe_get(k1, "range", "loc"),
            "range_pos_1h": _safe_get(k1, "range", "pos"),
            "ema20_slope_4h_pct": k4.get("ema20_slope_pct") if isinstance(k4, dict) else None,
            "rsi14_1h": k1.get("rsi14") if isinstance(k1, dict) else None,
            "atr14_pct_1h": atr_pct,
        },
    }

    prepared = {
        "symbol": sym,
        "price": {
            "now": px.get("px_now"),
            "chg_1h_pct": px.get("px_1h"),
            "chg_4h_pct": px.get("px_4h"),
            "chg_24h_pct": px.get("px_24h"),
            "vol_1h": px.get("vol_1h"),
        },
        "oi": {
            "now": oi.get("oi_now"),
            "chg_1h_pct": oi.get("oi_1h"),
            "chg_4h_pct": oi.get("oi_4h"),
            "chg_24h_pct": oi.get("oi_24h"),
            "oi_value_now": oi.get("oi_value_now"),
            "oi_value_chg_24h_pct": oi.get("oi_value_24h"),
        },
        "market": {
            "market_cap": mcfdv.get("market_cap"),
            "fdv": mcfdv.get("fdv"),
        },
        "kline_1h": k1,
        "kline_4h": k4,
        "twitter": tw_out,
        "derived": derived,
    }

    return {
        "symbol": sym,
        "use_llm": False,
        "errors": errors,
        "prepared": prepared,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="e.g. PUMPUSDT")
    ap.add_argument("--pretty", action="store_true", help="pretty-print json")
    args = ap.parse_args()

    out = run_prepare(args.symbol)
    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
