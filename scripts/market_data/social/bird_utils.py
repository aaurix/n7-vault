#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bird/X JSON helpers (salvage + time parsing + item extraction)."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Dict, List, Optional


def salvage_json(raw: str) -> Any:
    """Best-effort recover truncated JSON from bird outputs."""

    s = (raw or "").strip()
    if not s:
        raise ValueError("empty json")
    start = min([i for i in [s.find("{"), s.find("[")] if i != -1] or [0])
    tail = max(s.rfind("}"), s.rfind("]"))
    if tail != -1:
        s = s[start : tail + 1]
    else:
        s = s[start:]
    return json.loads(s)


def parse_bird_time(s: str, *, default_tz: Optional[dt.tzinfo] = None) -> Optional[dt.datetime]:
    """Parse bird time strings into timezone-aware datetime."""

    if not s:
        return None
    # example: "Wed Jan 24 13:37:22 +0000 2024"
    try:
        return dt.datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        pass
    try:
        ts = dt.datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=default_tz or dt.timezone.utc)
        return ts
    except Exception:
        return None


def extract_bird_items(obj: Any) -> List[Dict[str, Any]]:
    """Extract a list of tweet dicts from bird JSON payloads."""

    if isinstance(obj, dict):
        for k in ["tweets", "data", "items", "results", "timeline", "entries"]:
            v = obj.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


__all__ = ["salvage_json", "parse_bird_time", "extract_bird_items"]
