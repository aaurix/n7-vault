#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Trading-plan rendering helpers (LLM output).

Kept separate to keep build_summary simpler.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def normalize_plan_items(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(it)
    return out
