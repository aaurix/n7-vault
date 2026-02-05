#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified social card builder (TG + Twitter)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..models import PipelineContext, SocialCard
from ..market_data_helpers import (
    as_num as _as_num,
    fetch_cex_price as _fetch_cex_price,
    fetch_dex_market as _fetch_dex_market,
    norm_symbol as _norm_symbol,
)
from .actionable_normalization import _sentiment_from_actionable
from ..shared.evidence_cleaner import _clean_evidence_snippet
from ..shared.diagnostics import measure


def _split_drivers(text: str, *, max_n: int = 3) -> List[str]:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return []
    parts = [p.strip() for p in re.split(r"[;；,，、/|]+", t) if p.strip()]
    if len(parts) < 2:
        parts = [p.strip() for p in re.split(r"(?:和|并|以及|同时|与)", t) if p.strip()]
    if not parts:
        parts = [t]
    out: List[str] = []
    seen: set[str] = set()
    for p in parts:
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= max_n:
            break
    return out


def _clean_ev_list(ev: Any) -> List[str]:
    if isinstance(ev, list):
        ev_list = [str(x).strip() for x in ev if str(x).strip()]
    elif isinstance(ev, str):
        ev_list = [x.strip() for x in ev.split(";") if x.strip()]
    else:
        ev_list = []
    out: List[str] = []
    seen: set[str] = set()
    for x in ev_list:
        t = _clean_evidence_snippet(x, max_len=80)
        if not t:
            continue
        key = t.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= 2:
            break
    return out


def _extract_addr_from_texts(texts: List[str], resolver) -> str:
    for t in texts:
        _syms, addrs = resolver.extract_symbols_and_addrs(t, require_sol_digit=True)
        if addrs:
            return str(addrs[0])
    return ""


def _compose_one_liner(*, why_buy: str, why_not: str) -> str:
    parts: List[str] = []
    if why_buy:
        parts.append(f"买:{why_buy}")
    if why_not:
        parts.append(f"不买:{why_not}")
    return " | ".join(parts)


def _compose_signals(*, trigger: str, risk: str) -> str:
    parts: List[str] = []
    if trigger:
        parts.append(f"触发:{trigger}")
    if risk:
        parts.append(f"风险:{risk}")
    return "；".join(parts)


def _tg_card_from_actionable(it: Dict[str, Any], *, resolver, dex, cache: Dict[str, Dict[str, Any]]) -> Optional[SocialCard]:
    asset = str(it.get("asset_name") or it.get("asset") or it.get("symbol") or "").strip()
    sym = _norm_symbol(asset)
    if not sym:
        return None

    why_buy = str(it.get("why_buy") or "").strip()
    why_not = str(it.get("why_not_buy") or it.get("why_not") or "").strip()
    trigger = str(it.get("trigger") or "").strip()
    risk = str(it.get("risk") or "").strip()
    if not risk:
        risk = "情绪盘/消息噪音"

    ev = _clean_ev_list(it.get("evidence_snippets") or it.get("evidence") or [])
    drivers = _split_drivers(why_buy, max_n=3)
    if not drivers and trigger:
        drivers = _split_drivers(trigger, max_n=2)
    if not drivers and ev:
        drivers = _split_drivers(ev[0], max_n=2)
    addr = str(it.get("addr") or it.get("ca") or "").strip()
    if not addr and ev:
        addr = _extract_addr_from_texts(ev, resolver)

    sentiment = str(it.get("sentiment") or "").strip()
    if not sentiment:
        sentiment = _sentiment_from_actionable(why_buy=why_buy, why_not=why_not)

    one_liner = _compose_one_liner(why_buy=why_buy, why_not=why_not)
    signals = _compose_signals(trigger=trigger, risk=risk)

    price = _as_num(it.get("price"))
    mc = _as_num(it.get("market_cap") or it.get("marketCap"))
    fdv = _as_num(it.get("fdv"))
    chain = str(it.get("chain") or "").strip()

    if price is None or (mc is None and fdv is None) or not chain:
        key = addr or sym
        dm = cache.get(key)
        if dm is None:
            dm = _fetch_dex_market(addr, sym, dex)
            cache[key] = dm
        if price is None:
            price = dm.get("price")
        if mc is None:
            mc = dm.get("market_cap")
        if fdv is None:
            fdv = dm.get("fdv")
        if not chain:
            chain = dm.get("chain") or chain

    symbol_type = "onchain" if (addr or chain) else "cex"

    return {
        "source": "tg",
        "symbol": sym,
        "symbol_type": symbol_type,
        "addr": addr,
        "chain": chain,
        "price": price,
        "market_cap": mc,
        "fdv": fdv,
        "sentiment": sentiment or "中性",
        "one_liner": one_liner,
        "signals": signals,
        "evidence_snippets": ev,
        "drivers": drivers,
        "risk": risk,
    }


def _twitter_card_from_item(it: Dict[str, Any], *, resolver, dex, cache: Dict[str, Dict[str, Any]]) -> Optional[SocialCard]:
    sym = _norm_symbol(it.get("symbol") or it.get("sym") or it.get("asset_name") or it.get("asset") or "")
    if not sym:
        return None

    addr = str(it.get("addr") or it.get("ca") or "").strip()
    ev = _clean_ev_list(it.get("evidence_snippets") or it.get("snippets") or [])
    if not addr and ev:
        addr = _extract_addr_from_texts(ev, resolver)

    one_liner = str(it.get("one_liner") or "").strip()
    if not one_liner:
        why_buy = str(it.get("why_buy") or "").strip()
        why_not = str(it.get("why_not_buy") or it.get("why_not") or "").strip()
        one_liner = _compose_one_liner(why_buy=why_buy, why_not=why_not)

    signals = it.get("signals") or ""
    if isinstance(signals, list):
        signals = ";".join([str(x) for x in signals if str(x).strip()])
    signals = str(signals or "").strip()
    if not signals:
        trigger = str(it.get("trigger") or "").strip()
        risk = str(it.get("risk") or "").strip()
        signals = _compose_signals(trigger=trigger, risk=risk)

    sentiment = str(it.get("sentiment") or "").strip()
    if not sentiment:
        why_buy = str(it.get("why_buy") or "").strip()
        why_not = str(it.get("why_not_buy") or it.get("why_not") or "").strip()
        sentiment = _sentiment_from_actionable(why_buy=why_buy, why_not=why_not)

    price = _as_num(it.get("price"))
    mc = _as_num(it.get("market_cap") or it.get("marketCap"))
    fdv = _as_num(it.get("fdv"))
    chain = str(it.get("chain") or "").strip()

    symbol_type_raw = str(it.get("symbol_type") or "").strip().lower()
    symbol_type = symbol_type_raw or ("onchain" if (addr or chain) else "cex")

    if price is None or (mc is None and fdv is None) or (symbol_type == "onchain" and not chain):
        key = addr or sym
        dm = cache.get(key)
        if dm is None:
            dm = _fetch_dex_market(addr, sym, dex)
            cache[key] = dm
        if price is None:
            price = dm.get("price")
        if mc is None:
            mc = dm.get("market_cap")
        if fdv is None:
            fdv = dm.get("fdv")
        if not chain:
            chain = dm.get("chain") or chain

    if not symbol_type_raw and (addr or chain):
        symbol_type = "onchain"

    if symbol_type == "cex" and price is None:
        price = _fetch_cex_price(sym)

    return {
        "source": "twitter",
        "symbol": sym,
        "symbol_type": symbol_type,
        "addr": addr,
        "chain": chain,
        "price": price,
        "market_cap": mc,
        "fdv": fdv,
        "sentiment": sentiment or "中性",
        "one_liner": one_liner,
        "signals": signals,
        "evidence_snippets": ev,
    }


def _interleave_cards(a: List[SocialCard], b: List[SocialCard]) -> List[SocialCard]:
    out: List[SocialCard] = []
    seen: set[str] = set()
    ia = 0
    ib = 0
    while ia < len(a) or ib < len(b):
        if ia < len(a):
            card = a[ia]
            ia += 1
            sym = str(card.get("symbol") or "")
            if sym and sym not in seen:
                seen.add(sym)
                out.append(card)
        if ib < len(b):
            card = b[ib]
            ib += 1
            sym = str(card.get("symbol") or "")
            if sym and sym not in seen:
                seen.add(sym)
                out.append(card)
    return out


def self_check_social_cards() -> Dict[str, Any]:
    class _DummyResolver:
        def extract_symbols_and_addrs(self, text: str, require_sol_digit: bool = False):
            return [], []

    sample = {
        "asset_name": "TEST",
        "why_buy": "上所预期，资金流入，生态扩张",
        "why_not_buy": "",
        "trigger": "突破前高",
        "risk": "解锁压力",
        "evidence_snippets": ["测试1", "测试2"],
        "price": 1.23,
        "market_cap": 1234567,
        "fdv": 2345678,
        "chain": "sol",
    }

    card = _tg_card_from_actionable(sample, resolver=_DummyResolver(), dex=object(), cache={})
    drivers = card.get("drivers") if isinstance(card, dict) else []
    risk = card.get("risk") if isinstance(card, dict) else None
    ok = bool(card) and isinstance(drivers, list) and 2 <= len(drivers) <= 3 and risk == "解锁压力"
    return {"ok": ok, "drivers": drivers, "risk": risk}


def build_social_cards(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "social_cards")

    resolver = ctx.resolver
    dex = ctx.dex
    cache: Dict[str, Dict[str, Any]] = {}

    tw_cards: List[SocialCard] = []
    for it in (ctx.twitter_topics or [])[:6]:
        if not isinstance(it, dict):
            continue
        try:
            card = _twitter_card_from_item(it, resolver=resolver, dex=dex, cache=cache)
        except Exception as e:
            ctx.errors.append(f"social_cards_twitter_failed:{type(e).__name__}:{e}")
            continue
        if card:
            tw_cards.append(card)

    tg_cards: List[SocialCard] = []
    for it in (ctx.narratives or [])[:6]:
        if not isinstance(it, dict):
            continue
        asset = it.get("asset_name") or it.get("asset") or it.get("symbol")
        if not asset:
            continue
        try:
            card = _tg_card_from_actionable(it, resolver=resolver, dex=dex, cache=cache)
        except Exception as e:
            ctx.errors.append(f"social_cards_tg_failed:{type(e).__name__}:{e}")
            continue
        if card:
            tg_cards.append(card)

    ctx.perf["social_cards_twitter"] = float(len(tw_cards))
    ctx.perf["social_cards_tg"] = float(len(tg_cards))

    ctx.social_cards = _interleave_cards(tw_cards, tg_cards)
    done()
