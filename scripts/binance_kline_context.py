#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch quick K-line context for a Binance USDT symbol (futures) using public endpoints.

Usage:
  python3 binance_kline_context.py PTBUSDT --interval 5m --lookback 60

Outputs one compact line (Chinese) suitable for hourly summaries.

No API key required.
"""

import argparse
import json
import math
import sys
from typing import Optional, List
from urllib.request import urlopen, Request
from urllib.parse import urlencode

FAPI = "https://fapi.binance.com"


def get_klines(symbol: str, interval: str, limit: int):
    qs = urlencode({"symbol": symbol, "interval": interval, "limit": str(limit)})
    url = f"{FAPI}/fapi/v1/klines?{qs}"
    req = Request(url, headers={"User-Agent": "clawdbot/1.0"})
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def atr(highs, lows, closes, n=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < n:
        return None
    # simple moving average ATR
    return sum(trs[-n:]) / n


def sma(xs: List[float], n: int) -> Optional[float]:
    if len(xs) < n or n <= 0:
        return None
    return sum(xs[-n:]) / n


def ema(xs: List[float], n: int) -> Optional[float]:
    if len(xs) < n or n <= 1:
        return None
    k = 2 / (n + 1)
    e = xs[0]
    for x in xs[1:]:
        e = x * k + e * (1 - k)
    return e


def rsi(closes: List[float], n: int = 14) -> Optional[float]:
    if len(closes) < n + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(-n, 0):
        ch = closes[i] - closes[i - 1]
        if ch >= 0:
            gains += ch
        else:
            losses += abs(ch)
    if gains + losses == 0:
        return 50.0
    rs = gains / losses if losses > 0 else 999.0
    return 100 - (100 / (1 + rs))


def swing_levels(highs: List[float], lows: List[float], window: int = 20) -> tuple[Optional[float], Optional[float]]:
    if len(highs) < window or len(lows) < window:
        return None, None
    return max(highs[-window:]), min(lows[-window:])


def pct(a, b):
    if b == 0:
        return None
    return (a - b) / b * 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="e.g. PTBUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--lookback", type=int, default=60, help="number of candles")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    sym = args.symbol.upper()
    kl = get_klines(sym, args.interval, args.lookback)
    if not kl or len(kl) < 20:
        print(f"{sym}: K线数据不足")
        return 0

    # kline: [openTime, open, high, low, close, volume, closeTime, ...]
    opens = [float(x[1]) for x in kl]
    highs = [float(x[2]) for x in kl]
    lows = [float(x[3]) for x in kl]
    closes = [float(x[4]) for x in kl]
    vols = [float(x[5]) for x in kl]

    last = closes[-1]
    first = closes[0]
    chg = pct(last, first)
    hi = max(highs)
    lo = min(lows)
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5
    a = atr(highs, lows, closes, n=14)

    # key levels
    sw_hi, sw_lo = swing_levels(highs, lows, window=min(20, len(highs)))

    # crude trend by EMA20 slope (last vs previous)
    ema20 = ema(closes, 20)
    ema20_prev = ema(closes[:-1], 20) if len(closes) > 21 else None
    ema_slope = None
    if ema20 is not None and ema20_prev is not None:
        ema_slope = pct(ema20, ema20_prev)

    r = rsi(closes, 14)

    vol_last = vols[-1] if vols else None
    vol_ma20 = sma(vols, 20)
    vol_ratio = (vol_last / vol_ma20) if (vol_last is not None and vol_ma20) else None

    # location label
    if pos > 0.85:
        loc = "靠近区间高位"
    elif pos < 0.15:
        loc = "靠近区间低位"
    else:
        loc = "位于区间中部"

    if args.json:
        out = {
            "symbol": sym,
            "interval": args.interval,
            "lookback": args.lookback,
            "chg_pct": chg,
            "range": {"lo": lo, "hi": hi, "pos": pos, "loc": loc},
            "last": last,
            "atr14": a,
            "swing": {"hi": sw_hi, "lo": sw_lo},
            "ema20": ema20,
            "ema20_slope_pct": ema_slope,
            "rsi14": r,
            "volume": {"last": vol_last, "ma20": vol_ma20, "ratio": vol_ratio},
        }
        print(json.dumps(out, ensure_ascii=False))
        return 0

    atr_txt = "?" if a is None else f"{a:.4g}"
    chg_txt = "?" if chg is None else f"{chg:+.1f}%"

    print(f"{sym} {args.interval}近{args.lookback}根: {chg_txt}，区间[{lo:.4g}~{hi:.4g}]，现价{last:.4g}（{loc}），ATR14≈{atr_txt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
