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

from .binance_futures import oi_changes, price_changes


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
    for s in (oi_signals or [])[:top_n]:
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
    errors = errors or []

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
            out.append(
                {
                    "symbol": it.get("symbol") or "",
                    "bias": it.get("bias") or "观望",
                    "setup": it.get("setup") or "",
                    "triggers": it.get("triggers") if isinstance(it.get("triggers"), list) else [],
                    "invalidation": it.get("invalidation") or "",
                    "targets": it.get("targets") if isinstance(it.get("targets"), list) else [],
                    "risk_notes": it.get("risk_notes") if isinstance(it.get("risk_notes"), list) else [],
                }
            )
        return out
    except Exception as e:
        errors.append(f"{tag}_failed:{e}")
        return []
