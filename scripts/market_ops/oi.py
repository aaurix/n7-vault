#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OI/Price signal parsing from 方程式频道."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_TICKER_EXCLUDE = {"BTC", "ETH", "SOL", "BNB", "BSC", "BASE", "USDT", "USDC", "USD", "FDV", "MCAP", "DEX", "GMGN", "OI", "CA"}


def parse_oi_signals(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract {symbol, dir, oi, p1h, p24h} from messages.

    Supports both:
    - "OI +12.3%"
    - "openinterest +12.3%"
    - "未平仓合约增加12.3%"
    """

    out: List[Dict[str, Any]] = []

    sym_re = re.compile(r"\b([A-Z0-9]{2,12})\b")
    oi_re = re.compile(r"(?:OI|openinterest|未平仓合约)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%", re.IGNORECASE)
    h1_re = re.compile(r"(?:3600秒|1h|1H|1小时|1小時)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%")
    h24_re = re.compile(r"(?:24h|24H|24小时|24小時)[^0-9\-+]*([+\-]?\d+(?:\.\d+)?)%")

    for m in messages:
        t = (m.get("raw_text") or m.get("text") or "").strip()
        if not t:
            continue
        oi_m = oi_re.search(t)
        if not oi_m:
            continue
        oi = float(oi_m.group(1))

        h1_m = h1_re.search(t)
        h24_m = h24_re.search(t)
        p1h = float(h1_m.group(1)) if h1_m else None
        p24h = float(h24_m.group(1)) if h24_m else None

        sym = None
        head = t[:100]
        for cand in sym_re.findall(head):
            if cand in _TICKER_EXCLUDE:
                continue
            if cand.isdigit():
                continue
            sym = cand
            break
        if not sym:
            continue

        direction = "↑" if (p1h is not None and p1h > 0) or (oi > 0) else "↓"
        out.append({"symbol": sym, "dir": direction, "oi": oi, "p1h": p1h, "p24h": p24h, "raw": t[:220]})

    # rank
    def score(x):
        return (abs(x.get("oi") or 0), abs(x.get("p1h") or 0))

    out.sort(key=score, reverse=True)

    seen = set()
    uniq = []
    for it in out:
        if it["symbol"] in seen:
            continue
        seen.add(it["symbol"])
        uniq.append(it)
    return uniq[:8]
