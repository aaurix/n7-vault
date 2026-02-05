#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Binance kline fetcher helpers.

Summarizes kline arrays into compact indicators for downstream pipelines.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from scripts.market_data.exchange.binance_futures import get_klines


def _as_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _ema_last(values: Sequence[float], period: int) -> tuple[Optional[float], Optional[float]]:
    if len(values) < period:
        return None, None
    k = 2.0 / (period + 1)
    ema = sum(values[:period]) / float(period)
    ema_prev: Optional[float] = None
    for v in values[period:]:
        ema_prev = ema
        ema = v * k + ema * (1.0 - k)
    return ema, ema_prev


def _rsi_last(values: Sequence[float], period: int = 14) -> Optional[float]:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        gain = max(diff, 0.0)
        loss = max(-diff, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_last(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def summarize_klines(klines: List[List[Any]], *, interval: str) -> Dict[str, Any]:
    rows = [r for r in (klines or []) if isinstance(r, (list, tuple)) and len(r) >= 6]
    if not rows:
        return {}

    highs: List[float] = []
    lows: List[float] = []
    closes: List[float] = []
    volumes: List[float] = []

    for r in rows:
        o = _as_float(r[1])
        h = _as_float(r[2])
        l = _as_float(r[3])
        c = _as_float(r[4])
        v = _as_float(r[5])
        if h is None or l is None or c is None or v is None:
            continue
        highs.append(h)
        lows.append(l)
        closes.append(c)
        volumes.append(v)

    if not closes:
        return {}

    last = closes[-1]
    first = closes[0]
    chg_pct = None if first == 0 else (last - first) / first * 100.0

    lo = min(lows)
    hi = max(highs)
    pos = None if hi == lo else (last - lo) / (hi - lo)
    if pos is None:
        loc = None
    elif pos < 0.25:
        loc = "low"
    elif pos > 0.75:
        loc = "high"
    else:
        loc = "mid"

    ema20, ema20_prev = _ema_last(closes, 20)
    ema20_slope_pct = None
    if ema20 is not None and ema20_prev:
        if ema20_prev != 0:
            ema20_slope_pct = (ema20 - ema20_prev) / ema20_prev * 100.0

    rsi14 = _rsi_last(closes, 14)
    atr14 = _atr_last(highs, lows, closes, 14)

    vol_last = volumes[-1] if volumes else None
    vol_avg = None
    vol_ratio = None
    if len(volumes) > 1:
        vol_avg = sum(volumes[:-1]) / float(len(volumes) - 1)
        if vol_avg:
            vol_ratio = vol_last / vol_avg if vol_last is not None else None

    return {
        "interval": interval,
        "last": last,
        "chg_pct": chg_pct,
        "range": {"lo": lo, "hi": hi, "pos": pos, "loc": loc},
        "swing": {"hi": hi, "lo": lo},
        "ema20": ema20,
        "ema20_slope_pct": ema20_slope_pct,
        "rsi14": rsi14,
        "atr14": atr14,
        "volume": {"last": vol_last, "avg": vol_avg, "ratio": vol_ratio},
    }


def run_kline_json(symbol: str, *, interval: str, lookback: int = 80, timeout_s: int = 18) -> Dict[str, Any]:
    try:
        klines = get_klines(symbol, interval, lookback, timeout=timeout_s)
    except Exception:
        return {}
    return summarize_klines(klines, interval=interval)
