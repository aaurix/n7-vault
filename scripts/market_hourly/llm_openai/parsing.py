#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Parsing helpers for LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def parse_json_object(s: str) -> Optional[Dict[str, Any]]:
    """Parse a JSON object from a string, with best-effort recovery."""

    if not s:
        return None
    s2 = s.strip()
    try:
        out = json.loads(s2)
        return out if isinstance(out, dict) else None
    except Exception:
        pass

    # Strip fenced code blocks
    if "```" in s2:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s2, re.S | re.I)
        if m:
            try:
                out = json.loads(m.group(1))
                return out if isinstance(out, dict) else None
            except Exception:
                pass

    # Best-effort: take the first {...} span
    i = s2.find("{")
    j = s2.rfind("}")
    if 0 <= i < j:
        frag = s2[i : j + 1]
        try:
            out = json.loads(frag)
            return out if isinstance(out, dict) else None
        except Exception:
            return None
    return None


__all__ = ["parse_json_object"]
