#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Binance kline fetcher helpers.

Wraps scripts/binance_kline_context.py JSON output into a reusable function.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from market_ops.utils.paths import repo_root


BINANCE_KLINE_SCRIPT: Path = repo_root() / "scripts" / "binance_kline_context.py"


def run_kline_json(symbol: str, *, interval: str, lookback: int = 80, timeout_s: int = 18) -> Dict[str, Any]:
    cmd = [
        "python3",
        str(BINANCE_KLINE_SCRIPT),
        symbol,
        "--interval",
        interval,
        "--lookback",
        str(lookback),
        "--json",
    ]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s)
        raw = (p.stdout or "").strip().splitlines()[:1]
        if not raw:
            return {}
        return json.loads(raw[0])
    except Exception:
        return {}
