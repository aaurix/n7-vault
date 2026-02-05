#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Binance USDT-M futures public data helpers (no API key).

Used to upgrade OI/price/volume stats quality for the hourly pipeline.

Endpoints:
- /fapi/v1/klines
- /fapi/v1/openInterest
- /futures/data/openInterestHist
- /fapi/v1/premiumIndex (markPrice)

All calls are best-effort and return {} / [] on failure.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .exchange_ccxt import fetch_ohlcv, fetch_ticker_last, fetch_open_interest_history

FAPI = "https://fapi.binance.com"


def _get_json(path: str, params: Dict[str, Any], *, timeout: int = 10) -> Any:
    qs = urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{FAPI}{path}?{qs}" if qs else f"{FAPI}{path}"
    req = Request(url, headers={"User-Agent": "clawdbot-hourly/1.0"})
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_klines(symbol: str, interval: str, limit: int, *, timeout: int = 10) -> List[List[Any]]:
    """Return raw Binance-style klines.

    Prefer ccxt OHLCV (more stable / consistent), then fallback to native HTTP.
    Output is normalized to Binance kline-like arrays where possible.
    """

    # ccxt OHLCV: [ts, o, h, l, c, v]
    ohlcv = fetch_ohlcv(symbol, interval, limit)
    if ohlcv:
        out: List[List[Any]] = []
        for row in ohlcv:
            try:
                ts, o, h, l, c, v = row
                out.append([ts, str(o), str(h), str(l), str(c), str(v), None, None, None, None, None, None])
            except Exception:
                continue
        return out

    try:
        data = _get_json("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval, "limit": limit}, timeout=timeout)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_mark_price(symbol: str, *, timeout: int = 10) -> Optional[float]:
    # prefer ccxt ticker last (best-effort)
    last = fetch_ticker_last(symbol)
    if last is not None:
        return last
    try:
        data = _get_json("/fapi/v1/premiumIndex", {"symbol": symbol.upper()}, timeout=timeout)
        mp = data.get("markPrice") if isinstance(data, dict) else None
        return float(mp) if mp is not None else None
    except Exception:
        return None


def get_open_interest(symbol: str, *, timeout: int = 10) -> Optional[float]:
    try:
        data = _get_json("/fapi/v1/openInterest", {"symbol": symbol.upper()}, timeout=timeout)
        oi = data.get("openInterest") if isinstance(data, dict) else None
        return float(oi) if oi is not None else None
    except Exception:
        return None


def get_open_interest_hist(symbol: str, period: str, limit: int, *, timeout: int = 10) -> List[Dict[str, Any]]:
    """Return list of {sumOpenInterest, sumOpenInterestValue, timestamp}.

    Prefer ccxt fetchOpenInterestHistory when supported, fallback to Binance native endpoint.

    period: 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
    """

    rows = fetch_open_interest_history(symbol, timeframe=period, limit=limit)
    if rows:
        out: List[Dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            # try to normalize common keys
            ts = r.get("timestamp") or r.get("datetime")
            oi_amt = r.get("openInterest") or r.get("openInterestAmount") or r.get("amount")
            oi_val = r.get("openInterestValue") or r.get("openInterestNotional") or r.get("value")
            out.append({"timestamp": ts, "sumOpenInterest": oi_amt, "sumOpenInterestValue": oi_val})
        return out

    try:
        data = _get_json(
            "/futures/data/openInterestHist",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
            timeout=timeout,
        )
        return data if isinstance(data, list) else []
    except Exception:
        return []


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None:
        return None
    if old == 0:
        return None
    return (new - old) / old * 100.0


def oi_changes(symbol: str) -> Dict[str, Optional[float]]:
    """Compute OI % changes for 1h/4h/24h (best-effort).

    Also returns OI notional value (USD) now + 24h change when available.
    """

    out: Dict[str, Optional[float]] = {
        "oi_now": None,
        "oi_1h": None,
        "oi_4h": None,
        "oi_24h": None,
        "oi_value_now": None,
        "oi_value_24h": None,
    }

    out["oi_now"] = get_open_interest(symbol)

    h1 = get_open_interest_hist(symbol, "1h", 2)
    if len(h1) >= 2:
        out["oi_1h"] = pct_change(float(h1[-1].get("sumOpenInterest") or 0), float(h1[-2].get("sumOpenInterest") or 0))

    h4 = get_open_interest_hist(symbol, "4h", 2)
    if len(h4) >= 2:
        out["oi_4h"] = pct_change(float(h4[-1].get("sumOpenInterest") or 0), float(h4[-2].get("sumOpenInterest") or 0))

    h24 = get_open_interest_hist(symbol, "1h", 25)
    if len(h24) >= 2:
        last = h24[-1]
        first = h24[0]
        out["oi_24h"] = pct_change(float(last.get("sumOpenInterest") or 0), float(first.get("sumOpenInterest") or 0))
        try:
            out["oi_value_now"] = float(last.get("sumOpenInterestValue")) if last.get("sumOpenInterestValue") is not None else None
            out["oi_value_24h"] = pct_change(float(last.get("sumOpenInterestValue") or 0), float(first.get("sumOpenInterestValue") or 0))
        except Exception:
            pass

    return out


def price_changes(symbol: str) -> Dict[str, Optional[float]]:
    """Compute price % changes for 1h/4h/24h using kline closes."""
    out: Dict[str, Optional[float]] = {"px_now": None, "px_1h": None, "px_4h": None, "px_24h": None, "vol_1h": None}

    # 1h last close + last volume
    kl1 = get_klines(symbol, "1h", 25)
    if len(kl1) >= 2:
        closes = [float(x[4]) for x in kl1]
        vols = [float(x[5]) for x in kl1]
        out["px_now"] = closes[-1]
        out["vol_1h"] = vols[-1]
        out["px_1h"] = pct_change(closes[-1], closes[-2])
        out["px_24h"] = pct_change(closes[-1], closes[0])

    kl4 = get_klines(symbol, "4h", 2)
    if len(kl4) >= 2:
        closes = [float(x[4]) for x in kl4]
        out["px_4h"] = pct_change(closes[-1], closes[-2])

    # fallback to markPrice for now
    if out["px_now"] is None:
        out["px_now"] = get_mark_price(symbol)

    return out
