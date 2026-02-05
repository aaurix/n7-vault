#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""CCXT exchange wrapper (production).

Goals:
- Prefer ccxt for market data fetching (cleaner, more uniform).
- Feature-detect support for OI endpoints; fallback to native Binance HTTP when missing.
- Keep usage localized to this wrapper to avoid ccxt coupling everywhere.

This module is best-effort: returns None/[]/{} on failure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _try_import_ccxt():
    try:
        import ccxt  # type: ignore

        return ccxt
    except Exception:
        return None


_CCXT = None
_EXCHANGES: Dict[str, Any] = {}


def get_exchange(name: str):
    """Get a cached ccxt exchange instance by name.

    Common names:
    - "binance" (spot)
    - "binanceusdm" (Binance USDT-M futures)
    """

    global _CCXT
    if _CCXT is None:
        _CCXT = _try_import_ccxt()
    if _CCXT is None:
        return None

    if name in _EXCHANGES:
        return _EXCHANGES[name]

    try:
        klass = getattr(_CCXT, name)
        ex = klass({"enableRateLimit": True})
        _EXCHANGES[name] = ex
        return ex
    except Exception:
        return None


def fetch_ohlcv(symbol: str, timeframe: str, limit: int = 200, *, market: str = "binanceusdm") -> List[List[Any]]:
    """Return OHLCV list [ts, o, h, l, c, v] (best-effort)."""

    ex = get_exchange(market)
    if ex is None:
        return []
    try:
        # ccxt expects unified symbol like "BTC/USDT"
        sym = symbol.upper()
        if "/" not in sym and sym.endswith("USDT"):
            base = sym.replace("USDT", "")
            sym = f"{base}/USDT"
        return ex.fetch_ohlcv(sym, timeframe=timeframe, limit=limit) or []
    except Exception:
        return []


def fetch_ticker_last(symbol: str, *, market: str = "binanceusdm") -> Optional[float]:
    ex = get_exchange(market)
    if ex is None:
        return None
    try:
        sym = symbol.upper()
        if "/" not in sym and sym.endswith("USDT"):
            base = sym.replace("USDT", "")
            sym = f"{base}/USDT"
        t = ex.fetch_ticker(sym) or {}
        last = t.get("last")
        return float(last) if last is not None else None
    except Exception:
        return None


def fetch_open_interest_history(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 25,
    *,
    market: str = "binanceusdm",
) -> List[Dict[str, Any]]:
    """Try to fetch open interest history.

    Returns a list of dicts. Field names vary by exchange/ccxt version.
    Caller should normalize.
    """

    ex = get_exchange(market)
    if ex is None:
        return []

    try:
        if hasattr(ex, "has") and isinstance(ex.has, dict):
            if not ex.has.get("fetchOpenInterestHistory"):
                return []
        sym = symbol.upper()
        if "/" not in sym and sym.endswith("USDT"):
            base = sym.replace("USDT", "")
            sym = f"{base}/USDT"
        # ccxt signature: fetchOpenInterestHistory(symbol, timeframe?, since?, limit?, params?)
        fn = getattr(ex, "fetch_open_interest_history", None) or getattr(ex, "fetchOpenInterestHistory", None)
        if fn is None:
            return []
        rows = fn(sym, timeframe, None, limit, {})
        return rows if isinstance(rows, list) else []
    except Exception:
        return []
