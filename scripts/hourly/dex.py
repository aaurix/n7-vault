#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""DexScreener helpers."""

from __future__ import annotations

import json
import urllib.request as urlreq
from typing import Any, Dict, List, Optional


def dexscreener_search(q: str) -> List[Dict[str, Any]]:
    url = f"https://api.dexscreener.com/latest/dex/search?q={urlreq.quote(q)}"
    req = urlreq.Request(url, headers={"User-Agent": "clawdbot-hourly-summary/1.0"})
    try:
        with urlreq.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    return data.get("pairs") or []


def best_pair(pairs: List[Dict[str, Any]], symbol_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not pairs:
        return None
    if symbol_hint:
        p2 = [p for p in pairs if ((p.get("baseToken") or {}).get("symbol") or "").upper() == symbol_hint.upper()]
        if p2:
            pairs = p2

    def liq(p):
        return ((p.get("liquidity") or {}).get("usd") or 0) or 0

    def vol(p):
        return ((p.get("volume") or {}).get("h24") or 0) or 0

    return sorted(pairs, key=lambda p: (liq(p), vol(p)), reverse=True)[0]


def pair_metrics(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "chainId": p.get("chainId"),
        "dexId": p.get("dexId"),
        "url": p.get("url"),
        "pairAddress": p.get("pairAddress"),
        "baseSymbol": (p.get("baseToken") or {}).get("symbol"),
        "baseAddress": (p.get("baseToken") or {}).get("address"),
        "liquidityUsd": (p.get("liquidity") or {}).get("usd"),
        "vol24h": (p.get("volume") or {}).get("h24"),
        "chg1h": (p.get("priceChange") or {}).get("h1"),
        "chg24h": (p.get("priceChange") or {}).get("h24"),
        "fdv": p.get("fdv"),
        "marketCap": p.get("marketCap"),
    }


def enrich_symbol(sym: str) -> Optional[Dict[str, Any]]:
    pairs = dexscreener_search(sym)
    best = best_pair(pairs, symbol_hint=sym)
    if not best:
        return None
    return pair_metrics(best)


def resolve_addr_symbol(addr: str) -> Optional[str]:
    pairs = dexscreener_search(addr)
    best = best_pair(pairs)
    if not best:
        return None
    sym = ((best.get("baseToken") or {}).get("symbol") or "").upper().strip()
    return sym or None
