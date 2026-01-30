#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hourly TG+Twitter market/meme summary (production).

Contract:
- Prints exactly one JSON object to stdout for the cron delivery wrapper.
- Never crashes without emitting JSON (best-effort).

Implementation lives in hourly.market_summary_pipeline.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo


def _emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main() -> int:
    # Make ./scripts importable when executed as a script
    sys.path.insert(0, os.path.dirname(__file__))

    try:
        from hourly.market_summary_pipeline import run_pipeline  # type: ignore

        budget_s = float(os.environ.get("HOURLY_MARKET_SUMMARY_BUDGET_S", "240"))
        out = run_pipeline(total_budget_s=budget_s)
        _emit(out)
        return 0
    except Exception as e:
        # Worst-case fallback: still emit JSON.
        utc = ZoneInfo("UTC")
        now = dt.datetime.now(utc)
        iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        _emit(
            {
                "since": "",
                "until": iso,
                "hourKey": "",
                "summaryHash": "",
                "summary_whatsapp": "",
                "summary_markdown": "",
                "summary_markdown_path": "",
                "errors": [f"fatal_wrapper:{type(e).__name__}:{e}"],
                "elapsed_s": 0.0,
                "perf": {},
                "use_llm": False,
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
