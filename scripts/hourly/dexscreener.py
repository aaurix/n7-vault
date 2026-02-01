#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""DexScreener helpers with shared cache + throttle (shim)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .services.dexscreener_client import (
    DEFAULT_TTL_S,
    DexScreenerClient,
    get_shared_dexscreener_client,
)


def _client(cache_path: Optional[Path] = None) -> DexScreenerClient:
    return get_shared_dexscreener_client(cache_path=cache_path)


def dexscreener_json(
    url: str,
    *,
    ttl_s: int = DEFAULT_TTL_S,
    timeout_s: int = 12,
    cache_path: Optional[Path] = None,
) -> Optional[Any]:
    if not url:
        return None
    return _client(cache_path).json(url, ttl_s=ttl_s, timeout_s=timeout_s, cache_path=cache_path)


def dexscreener_search(q: str, *, ttl_s: int = DEFAULT_TTL_S) -> List[Dict[str, Any]]:
    return _client().search(q, ttl_s=ttl_s)


def best_pair(pairs: List[Dict[str, Any]], symbol_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    return DexScreenerClient.best_pair(pairs, symbol_hint=symbol_hint)


def pair_metrics(p: Dict[str, Any]) -> Dict[str, Any]:
    return DexScreenerClient.pair_metrics(p)


def enrich_symbol(sym: str) -> Optional[Dict[str, Any]]:
    return _client().enrich_symbol(sym)


def enrich_addr(addr: str) -> Optional[Dict[str, Any]]:
    return _client().enrich_addr(addr)


def resolve_addr_symbol(addr: str) -> Optional[str]:
    return _client().resolve_addr_symbol(addr)


__all__ = [
    "dexscreener_json",
    "dexscreener_search",
    "best_pair",
    "pair_metrics",
    "enrich_symbol",
    "enrich_addr",
    "resolve_addr_symbol",
]
