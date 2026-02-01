#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Viewpoint-thread extraction from human TG messages.

Design goals:
- token/CA-first: do not output vague topic threads without a concrete tradable symbol
- no raw quotes: output distilled bullets
- heat threshold: >=3 messages per thread (user preference)
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

from .filters import GENERIC_TOKENS, stance_from_texts
from .services.entity_resolver import EntityResolver, get_shared_entity_resolver


def _points_of(msgs: List[str]) -> List[str]:
    low = "\n".join(msgs).lower()
    pts: List[str] = []

    if any(k in low for k in ["alpha", "上alpha", "binance alpha", "上所", "上架", "上线", "list", "listing"]):
        pts.append("事件驱动：围绕上所/Alpha/上架预期在博弈")
    if any(k in low for k in ["收割", "砸", "dump", "出货", "割", "rug", "跑路"]):
        pts.append("风险预期偏高：担心砸盘/收割/出货")
    if any(k in low for k in ["跟单", "聪明钱", "鲸鱼", "insider", "wallet", "钱包"]):
        pts.append("信息博弈：围绕钱包/跟单的讨论增多")
    if any(k in low for k in ["回踩", "突破", "放量", "缩量", "支撑", "压力", "结构", "趋势"]):
        pts.append("结构交易语境：关注突破/回踩是否成立")
    if any(k in low for k in ["pump", "拉盘", "起飞", "冲", "fomo"]):
        pts.append("动量情绪更强：注意冲高回落与二次派发")

    # de-dup
    out: List[str] = []
    seen = set()
    for p in pts:
        if p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out[:3]


def extract_viewpoint_threads(
    human_texts: List[str],
    *,
    min_heat: int = 3,
    weak_heat: int = 2,
    resolver: EntityResolver | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Return {'strong': [...], 'weak': [...]} token threads.

    - strong: heat >= min_heat
    - weak: weak_heat <= heat < min_heat (used as additional context)

    Both require:
    - resolvable token/CA -> symbol
    - DexScreener match (real market)

    Note: when heat is high, we allow a generic point even if no clear trigger words,
    to avoid dropping otherwise strong threads.
    """

    resolver = resolver or get_shared_entity_resolver()
    dex_client = resolver.dex

    clusters: Dict[str, List[str]] = {}

    resolve_cache: Dict[str, str | None] = {}
    enrich_cache: Dict[str, Dict[str, Any] | None] = {}
    resolve_calls = 0
    enrich_calls = 0
    max_resolve_calls = 40
    max_enrich_calls = 30
    t0 = time.perf_counter()
    try:
        time_budget_s = float(os.environ.get("HOURLY_TG_VIEWPOINT_BUDGET_S") or 12.0)
    except Exception:
        time_budget_s = 12.0

    for t in human_texts:
        if time.perf_counter() - t0 > time_budget_s:
            break
        t = (t or "").strip()
        if not t:
            continue

        syms, addrs = resolver.extract_symbols_and_addrs(t)
        # Resolve CA -> symbol (budgeted + cached)
        for a in addrs[:2]:
            if a in resolve_cache:
                rs = resolve_cache[a]
            else:
                if resolve_calls >= max_resolve_calls:
                    continue
                rs = resolver.resolve_addr_symbol(a)
                resolve_cache[a] = rs
                resolve_calls += 1
            if rs and rs not in GENERIC_TOKENS:
                syms.append(rs)

        syms = [s for s in syms if s not in GENERIC_TOKENS]
        if not syms:
            continue

        # token-first key
        sym = syms[0]
        clusters.setdefault(sym, []).append(t)

    strong: List[Dict[str, Any]] = []
    weak: List[Dict[str, Any]] = []

    for sym, msgs in clusters.items():
        if time.perf_counter() - t0 > time_budget_s:
            break
        c = len(msgs)
        if c < weak_heat:
            continue

        pts = _points_of(msgs)
        if not pts:
            # For low-heat threads, allow empty points (avoid repetitive filler text).
            if c >= min_heat:
                pts = ["热度升温：讨论集中但共识不强，注意节奏与风险"]
            else:
                pts = []

        if sym in enrich_cache:
            dex = enrich_cache[sym]
        else:
            if enrich_calls >= max_enrich_calls:
                continue
            if time.perf_counter() - t0 > time_budget_s:
                break
            dex = dex_client.enrich_symbol(sym)
            enrich_cache[sym] = dex
            enrich_calls += 1
        if not dex:
            continue

        title = (
            f"{sym}（MC≈${_cn_num(dex.get('marketCap') or dex.get('fdv'))} "
            f"vol24≈${_cn_num(dex.get('vol24h'))} liq≈${_cn_num(dex.get('liquidityUsd'))}）"
        )
        item = {
            "title": title,
            "stance": stance_from_texts(msgs),
            "count": c,
            "entities": [sym],
            "points": pts,
            "sym": sym,
            # raw inputs (for LLM summarization; not rendered directly)
            "_msgs": msgs[:20],
            "_dex": dex,
        }

        if c >= min_heat:
            strong.append(item)
        elif c >= weak_heat:
            weak.append(item)

    strong.sort(key=lambda x: -int(x.get("count") or 0))
    weak.sort(key=lambda x: -int(x.get("count") or 0))
    return {"strong": strong, "weak": weak}


def _cn_num(x: Any) -> str:
    if x is None:
        return "?"
    try:
        if isinstance(x, str):
            x = float(x)
        if abs(x) >= 1e9:
            return f"{x/1e9:.1f}B"
        if abs(x) >= 1e6:
            return f"{x/1e6:.1f}M"
        if abs(x) >= 1e3:
            return f"{x/1e3:.1f}K"
        return f"{x:.0f}"
    except Exception:
        return str(x)
