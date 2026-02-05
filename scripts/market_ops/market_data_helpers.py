#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared market-data helpers (symbol normalization + price/marketcap lookups)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from scripts.market_data import get_shared_exchange_batcher


def as_num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def norm_symbol(val: Any) -> str:
    s = str(val or "").upper().strip()
    if s.startswith("$"):
        s = s[1:]
    return s


def pick_dex_market(dex: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(dex, dict):
        return {}
    return {
        "price": as_num(dex.get("priceUsd") or dex.get("price")),
        "market_cap": as_num(dex.get("marketCap") or dex.get("market_cap") or dex.get("mcap")),
        "fdv": as_num(dex.get("fdv") or dex.get("fully_diluted_valuation")),
        "chain": str(dex.get("chainId") or "").strip(),
    }


def fetch_dex_market(addr: str, sym: str, dex_client) -> Dict[str, Any]:
    dex = None
    if addr:
        dex = dex_client.enrich_addr(addr)
    if not dex and sym:
        dex = dex_client.enrich_symbol(sym)
    return pick_dex_market(dex or {})


def fetch_cex_price(sym: str) -> Optional[float]:
    s = norm_symbol(sym)
    if not s:
        return None
    sym2 = s if s.endswith("USDT") or "/" in s else f"{s}USDT"
    exchange = get_shared_exchange_batcher()
    px = exchange.ticker_last(sym2)
    if px is not None:
        return px
    try:
        sym3 = sym2.replace("/", "")
        return exchange.mark_price(sym3)
    except Exception:
        return None
