#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CoinGecko public API helper (no key) for market cap / FDV.

Design goals (production):
- Conservative matching: only return data when symbol->id mapping is unambiguous.
- Cache symbol->id mapping on disk to reduce API calls.

API:
- /api/v3/search?query=...
- /api/v3/coins/markets?vs_currency=usd&ids=...

Note: CoinGecko rate limits; keep calls minimal.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.coingecko.com/api/v3"


def _repo_root() -> str:
    here = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def _map_path() -> str:
    return os.path.join(_repo_root(), "memory", "coingecko_symbol_map.json")


def _get_json(path: str, params: Dict[str, Any], *, timeout: int = 12) -> Any:
    qs = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
    req = Request(url, headers={"User-Agent": "clawdbot-hourly/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _load_map() -> Dict[str, str]:
    p = _map_path()
    try:
        if os.path.exists(p):
            data = json.loads(open(p, "r", encoding="utf-8").read())
            return {str(k).upper(): str(v) for k, v in (data or {}).items() if k and v}
    except Exception:
        pass
    return {}


def _save_map(m: Dict[str, str]) -> None:
    p = _map_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(json.dumps(m, ensure_ascii=False, indent=2))
    except Exception:
        pass


def resolve_symbol_id(symbol: str) -> Optional[str]:
    """Resolve a ticker symbol to a CoinGecko coin id.

    Conservative:
    - Look at /search results.
    - Keep candidates whose symbol matches.
    - If exactly one match -> accept.
    - If multiple -> reject (None) to avoid mis-mapping.

    Cache is used for previously resolved symbols.
    """

    sym = (symbol or "").upper().strip()
    if not sym:
        return None

    m = _load_map()
    if sym in m:
        return m[sym]

    try:
        data = _get_json("/search", {"query": sym})
    except Exception:
        return None

    coins = (data.get("coins") if isinstance(data, dict) else None) or []
    cands = [c for c in coins if str((c or {}).get("symbol") or "").upper() == sym]

    if len(cands) != 1:
        return None

    cid = str(cands[0].get("id") or "").strip()
    if not cid:
        return None

    m[sym] = cid
    _save_map(m)
    return cid


def get_market_cap_fdv(symbol: str) -> Dict[str, Optional[float]]:
    """Return {market_cap, fdv} for the symbol if resolvable, else {}."""

    sym = (symbol or "").upper().strip()
    cid = resolve_symbol_id(sym)
    if not cid:
        return {}

    try:
        rows = _get_json(
            "/coins/markets",
            {
                "vs_currency": "usd",
                "ids": cid,
                "sparkline": "false",
            },
        )
    except Exception:
        return {}

    if not isinstance(rows, list) or not rows:
        return {}

    r = rows[0]
    mc = r.get("market_cap")
    fdv = r.get("fully_diluted_valuation")

    out: Dict[str, Optional[float]] = {}
    try:
        out["market_cap"] = float(mc) if mc is not None else None
    except Exception:
        out["market_cap"] = None

    try:
        out["fdv"] = float(fdv) if fdv is not None else None
    except Exception:
        out["fdv"] = None

    # Only return if at least one is present
    if out.get("market_cap") is None and out.get("fdv") is None:
        return {}

    return out
