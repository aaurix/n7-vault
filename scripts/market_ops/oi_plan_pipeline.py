#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OI trading plan pipeline (production).

Input: parsed OI signals + kline fetcher
Output: LLM plans (TopN)

Stability-first:
- time budget gating for LLM call
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .adapters.binance_futures import oi_changes, price_changes
from .twitter_context import twitter_context_for_symbol


def _summarize_twitter_views(tw: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize trader-like Twitter snippets into bull/bear points (no extra LLM).

    Output:
      {total, kept, bull_points, bear_points}
    """

    total = int(tw.get("total") or 0)
    kept = int(tw.get("kept") or 0)
    snips = tw.get("snippets") or []
    if not isinstance(snips, list):
        snips = []

    bull_kw = ["long", "buy", "bull", "bullish", "breakout", "break above", "break up", "support", "hold", "bid", "accumulate"]
    bear_kw = ["short", "sell", "bear", "bearish", "breakdown", "break below", "break down", "resistance", "reject", "distribution", "dump"]

    import re

    def _pick_level(t: str) -> Optional[str]:
        m = re.search(r"\b\d+\.\d+\b|\b0\.\d{3,}\b", t)
        return m.group(0) if m else None

    bull: List[str] = []
    bear: List[str] = []

    for raw in snips[:8]:
        t = str(raw or "").strip()
        if not t:
            continue
        low = t.lower()
        lvl = _pick_level(t)

        is_bull = any(k in low for k in bull_kw)
        is_bear = any(k in low for k in bear_kw)

        # Decide bucket
        if is_bull and not is_bear:
            if lvl and "break" in low:
                bull.append(f"提到突破 {lvl}")
            elif lvl and "support" in low:
                bull.append(f"提到支撑 {lvl}")
            else:
                bull.append(t[:60])
        elif is_bear and not is_bull:
            if lvl and "break" in low:
                bear.append(f"提到跌破 {lvl}")
            elif lvl and "resistance" in low:
                bear.append(f"提到压力 {lvl}")
            else:
                bear.append(t[:60])

        if len(bull) >= 2 and len(bear) >= 2:
            break

    # De-dup while keeping order
    def _uniq(xs: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for x in xs:
            k = x.strip().lower()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(x.strip())
        return out

    bull = _uniq(bull)[:2]
    bear = _uniq(bear)[:2]

    return {
        "total": total,
        "kept": kept,
        "bull_points": bull,
        "bear_points": bear,
    }


def build_oi_items(
    *,
    oi_signals: List[Dict[str, Any]],
    kline_fetcher: Callable[..., Dict[str, Any]],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """Build enriched items for trader plans.

    Includes:
    - current price
    - price change 1h/4h/24h
    - OI change 1h/4h/24h (best-effort)
    - 1h volume + volume ratio (from kline json if available)
    """

    items: List[Dict[str, Any]] = []
    for idx, s in enumerate((oi_signals or [])[:top_n]):
        sym = s.get("symbol")
        if not sym:
            continue

        k1 = kline_fetcher(sym, interval="1h", lookback=120)
        k4 = kline_fetcher(sym, interval="4h", lookback=80)

        px = price_changes(sym)
        oi = oi_changes(sym)

        # pull volume ratio from kline json
        vr = None
        vol_last = px.get("vol_1h")
        try:
            vj = (k1.get("volume") or {}) if isinstance(k1, dict) else {}
            vr = vj.get("ratio")
            if vol_last is None:
                vol_last = vj.get("last")
        except Exception:
            pass

        tw_ctx = None
        tw_sum = None
        if idx == 0:
            # Only for Top1 to keep cost + output length bounded.
            tw_ctx = twitter_context_for_symbol(sym, limit=8)
            # Keep raw snippets for LLM to summarize (no raw quotes shown to user).
            # Still keep a lightweight rule summary for debugging.
            tw_sum = _summarize_twitter_views(tw_ctx)

        items.append(
            {
                "symbol": sym,
                "price_now": px.get("px_now"),
                "price_1h": px.get("px_1h"),
                "price_4h": px.get("px_4h"),
                "price_24h": px.get("px_24h"),
                "vol_1h": vol_last,
                "vol_ratio": vr,
                "oi_now": oi.get("oi_now"),
                "oi_1h": oi.get("oi_1h"),
                "oi_4h": oi.get("oi_4h"),
                "oi_24h": oi.get("oi_24h"),
                # original signal fields (if available)
                "oi_signal": s.get("oi"),
                "p1h": s.get("p1h"),
                "p24h": s.get("p24h"),
                "flow": s.get("flow") or "",
                "kline_1h": k1,
                "kline_4h": k4,
                "twitter": tw_ctx,
                "twitter_summary": tw_sum,
            }
        )

    return items


def build_oi_plans(
    *,
    use_llm: bool,
    oi_items: List[Dict[str, Any]],
    llm_fn: Callable[..., Dict[str, Any]],
    time_budget_ok: Optional[Callable[[float], bool]] = None,
    budget_s: float = 45.0,
    top_n: int = 3,
    errors: Optional[List[str]] = None,
    tag: str = "oi_plan",
) -> List[Dict[str, Any]]:
    """Call LLM to generate trading plans."""

    time_budget_ok = time_budget_ok or (lambda _limit: True)
    if errors is None:
        errors = []

    if not use_llm:
        errors.append(f"{tag}_skipped:no_llm")
        return []
    if not oi_items:
        errors.append(f"{tag}_empty")
        return []
    if not time_budget_ok(budget_s):
        errors.append(f"{tag}_skipped:budget")
        return []

    try:
        pj = llm_fn(items=oi_items[:top_n])
        its = pj.get("items") if isinstance(pj, dict) else None
        if not isinstance(its, list):
            errors.append(f"{tag}_bad_output")
            return []

        out: List[Dict[str, Any]] = []
        for it in its[:top_n]:
            if not isinstance(it, dict):
                continue
            sym = it.get("symbol") or ""
            # attach twitter summary for top1 (by item order and symbol match)
            tw_sum = None
            try:
                if out == [] and oi_items and str(oi_items[0].get("symbol") or "") == str(sym):
                    tw_sum = oi_items[0].get("twitter_summary")
            except Exception:
                pass

            out.append(
                {
                    "symbol": sym,
                    "bias": it.get("bias") or "观望",
                    "setup": it.get("setup") or "",
                    "triggers": it.get("triggers") if isinstance(it.get("triggers"), list) else [],
                    "invalidation": it.get("invalidation") or "",
                    "targets": it.get("targets") if isinstance(it.get("targets"), list) else [],
                    "risk_notes": it.get("risk_notes") if isinstance(it.get("risk_notes"), list) else [],
                    # twitter summary fields are only expected for Top1
                    "twitter_quality": (it.get("twitter_quality") or "") if isinstance(it.get("twitter_quality"), str) else "",
                    "twitter_bull": (it.get("twitter_bull") or "") if isinstance(it.get("twitter_bull"), str) else "",
                    "twitter_bear": (it.get("twitter_bear") or "") if isinstance(it.get("twitter_bear"), str) else "",
                    "twitter_meta": oi_items[0].get("twitter") if (out == [] and oi_items and str(oi_items[0].get("symbol") or "") == str(sym)) else None,
                }
            )
        return out
    except Exception as e:
        errors.append(f"{tag}_failed:{e}")
        return []
