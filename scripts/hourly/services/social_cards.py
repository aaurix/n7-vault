#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified social card builder (TG + Twitter)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..binance_futures import get_mark_price
from ..exchange_ccxt import fetch_ticker_last
from ..models import PipelineContext, SocialCard
from .actionable_normalization import _sentiment_from_actionable
from .evidence_cleaner import _clean_evidence_snippet
from .pipeline_timing import measure


def _as_num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _norm_symbol(val: Any) -> str:
    s = str(val or "").upper().strip()
    if s.startswith("$"):
        s = s[1:]
    return s


def _pick_dex_market(dex: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(dex, dict):
        return {}
    return {
        "price": _as_num(dex.get("priceUsd") or dex.get("price")),
        "market_cap": _as_num(dex.get("marketCap") or dex.get("market_cap") or dex.get("mcap")),
        "fdv": _as_num(dex.get("fdv") or dex.get("fully_diluted_valuation")),
        "chain": str(dex.get("chainId") or "").strip(),
    }


def _fetch_dex_market(addr: str, sym: str, dex_client) -> Dict[str, Any]:
    dex = None
    if addr:
        dex = dex_client.enrich_addr(addr)
    if not dex and sym:
        dex = dex_client.enrich_symbol(sym)
    return _pick_dex_market(dex or {})


def _fetch_cex_price(sym: str) -> Optional[float]:
    s = _norm_symbol(sym)
    if not s:
        return None
    sym2 = s if s.endswith("USDT") or "/" in s else f"{s}USDT"
    px = fetch_ticker_last(sym2)
    if px is not None:
        return px
    try:
        sym3 = sym2.replace("/", "")
        return get_mark_price(sym3)
    except Exception:
        return None


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

    ev = _clean_ev_list(it.get("evidence_snippets") or it.get("evidence") or [])
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


def build_social_cards(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "social_cards")

    resolver = ctx.resolver
    dex = ctx.dex
    cache: Dict[str, Dict[str, Any]] = {}

    tw_cards: List[SocialCard] = []
    for it in (ctx.twitter_topics or [])[:6]:
        if not isinstance(it, dict):
            continue
        card = _twitter_card_from_item(it, resolver=resolver, dex=dex, cache=cache)
        if card:
            tw_cards.append(card)

    tg_cards: List[SocialCard] = []
    for it in (ctx.narratives or [])[:6]:
        if not isinstance(it, dict):
            continue
        asset = it.get("asset_name") or it.get("asset") or it.get("symbol")
        if not asset:
            continue
        card = _tg_card_from_actionable(it, resolver=resolver, dex=dex, cache=cache)
        if card:
            tg_cards.append(card)

    ctx.perf["social_cards_twitter"] = float(len(tw_cards))
    ctx.perf["social_cards_tg"] = float(len(tg_cards))

    ctx.social_cards = _interleave_cards(tw_cards, tg_cards)
    done()
