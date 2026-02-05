#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Twitter/X supplement signal cards."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..llm_openai import summarize_twitter_ca_viewpoints
from ..models import PipelineContext
from ..market_data_helpers import (
    as_num as _as_num,
    fetch_cex_price as _fetch_cex_price,
    fetch_dex_market as _fetch_dex_market,
    norm_symbol as _norm_symbol,
)
from .actionable_normalization import _fallback_actionables_from_radar
from .evidence_cleaner import _clean_evidence_snippet
from .diagnostics import log_llm_failure
from .diagnostics import measure


def build_twitter_ca_topics(ctx: PipelineContext) -> None:
    """Twitter signal cards (aux supplement)."""

    done = measure(ctx.perf, "twitter_ca_topics")

    dex_client = ctx.dex

    # Build candidate list from meme radar items with Twitter evidence.
    candidates: List[Dict[str, Any]] = []
    for it in (ctx.radar_items or [])[:25]:
        ev = it.get("twitter_evidence") or {}
        snips = ev.get("snippets") or []
        if not snips:
            continue
        dex = it.get("dex") or {}
        sym = _norm_symbol(dex.get("baseSymbol") or it.get("symbol") or it.get("sym"))
        addr = str(it.get("addr") or dex.get("baseAddress") or "").strip()
        if not sym and not addr:
            continue
        ident = str(it.get("sourceKey") or addr or sym)
        candidates.append({"id": ident, "sym": sym, "ca": addr, "snippets": snips, "radar": it})
        if len(candidates) >= 8:
            break

    ctx.perf["twitter_candidates"] = float(len(candidates))

    llm_items: List[Dict[str, Any]] = []
    if ctx.use_llm and candidates and (not ctx.budget.over(reserve_s=95.0)):
        try:
            llm_in = [
                {
                    "id": c.get("id"),
                    "sym": c.get("sym"),
                    "ca": c.get("ca"),
                    "evidence": {"snippets": (c.get("snippets") or [])[:6]},
                }
                for c in candidates
            ]
            out = summarize_twitter_ca_viewpoints(items=llm_in)
            raw_items = out.get("items") if isinstance(out, dict) else None
            parse_failed = bool(isinstance(out, dict) and out.get("_parse_failed"))
            raw = str(out.get("raw") or "") if isinstance(out, dict) else ""
            if parse_failed:
                log_llm_failure(ctx, "twitter_viewpoints_llm_parse_failed", raw=raw)
            if isinstance(raw_items, list):
                llm_items = [it for it in raw_items if isinstance(it, dict)]
            elif isinstance(out, dict) and not parse_failed:
                log_llm_failure(ctx, "twitter_viewpoints_llm_schema_invalid", raw=raw)
            if not llm_items and not parse_failed:
                log_llm_failure(ctx, "twitter_viewpoints_llm_empty", raw=raw)
        except Exception as e:
            log_llm_failure(ctx, "twitter_viewpoints_llm_failed", exc=e)

    # Index LLM outputs by id/symbol/ca for matching
    llm_map: Dict[str, Dict[str, Any]] = {}
    for it in llm_items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "").strip()
        if iid:
            llm_map[iid] = it
        sym = _norm_symbol(it.get("sym") or it.get("symbol"))
        if sym and sym not in llm_map:
            llm_map[sym] = it
        ca = str(it.get("ca") or it.get("addr") or "").strip()
        if ca and ca not in llm_map:
            llm_map[ca] = it

    # Build signal cards with price/market cap.
    cards: List[Dict[str, Any]] = []
    seen: set[str] = set()
    dex_cache: Dict[str, Dict[str, Any]] = {}

    for c in candidates[:8]:
        radar = c.get("radar") if isinstance(c.get("radar"), dict) else {}
        dex = radar.get("dex") if isinstance(radar.get("dex"), dict) else {}

        base_sym = _norm_symbol(c.get("sym"))
        addr = str(c.get("ca") or "").strip()
        summ = llm_map.get(str(c.get("id") or "")) or llm_map.get(base_sym) or llm_map.get(addr) or {}

        sym = _norm_symbol(summ.get("sym") or summ.get("symbol") or base_sym)
        if not sym and addr:
            sym = base_sym or addr
        if not sym or sym in seen:
            continue

        symbol_type = "onchain" if (addr or dex.get("baseAddress")) else "cex"

        market = _pick_dex_market(dex)
        price = market.get("price")
        mc = market.get("market_cap")
        fdv = market.get("fdv")
        chain = market.get("chain")

        if symbol_type == "onchain" and (price is None or (mc is None and fdv is None)):
            key = addr or sym
            dm = dex_cache.get(key)
            if dm is None:
                dm = _fetch_dex_market(addr, sym, dex_client)
                dex_cache[key] = dm
            if price is None:
                price = dm.get("price")
            if mc is None:
                mc = dm.get("market_cap")
            if fdv is None:
                fdv = dm.get("fdv")
            if not chain:
                chain = dm.get("chain") or chain

        if symbol_type == "cex" and price is None:
            price = _fetch_cex_price(sym)

        sig = summ.get("signals") or ""
        if isinstance(sig, list):
            sig = ";".join([str(x) for x in sig if str(x).strip()])

        one_liner = str(summ.get("one_liner") or "").strip()
        sentiment = str(summ.get("sentiment") or "").strip() or "中性"

        ev2 = [_clean_evidence_snippet(str(s), max_len=80) for s in (c.get("snippets") or [])[:4]]
        ev2 = [x for x in ev2 if x][:2]

        cards.append(
            {
                "card_type": "twitter_signal",
                "symbol": sym,
                "symbol_type": symbol_type,
                "addr": addr,
                "chain": chain,
                "price": price,
                "market_cap": mc,
                "fdv": fdv,
                "sentiment": sentiment,
                "one_liner": one_liner,
                "signals": sig,
                "evidence_snippets": ev2,
            }
        )
        seen.add(sym)
        if len(cards) >= 5:
            break

    # Fallback: use radar evidence when no cards are built
    if not cards:
        items = _fallback_actionables_from_radar(ctx.radar_items, limit=5)
        ctx.twitter_topics = items[:5]
        done()
        return

    ctx.twitter_topics = cards[:5]
    done()
