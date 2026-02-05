#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bird (X/Twitter) provider helpers."""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List, Optional

from . import bird_utils


_AUTH_PATTERNS = [
    "missing auth_token",
    "missing ct0",
    "missing required credentials",
    "no twitter cookies found",
    "failed to read macos keychain",
]


def _run_bird(cmd: List[str], *, timeout_s: int) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s)
    if p.returncode != 0:
        raise RuntimeError(p.stderr or "bird failed")
    return p.stdout or ""


def _parse_bird_json(raw: str) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        try:
            return bird_utils.salvage_json(raw)
        except Exception:
            return None


def _detect_auth_error(raw: str) -> bool:
    text = (raw or "").lower()
    if not text:
        return False
    return any(p in text for p in _AUTH_PATTERNS)


def bird_search(query: str, *, n: int = 30, timeout_s: int = 18) -> List[Dict[str, Any]]:
    if not query:
        return []
    try:
        raw = _run_bird(["bird", "search", query, "-n", str(n), "--json"], timeout_s=timeout_s)
        if _detect_auth_error(raw):
            return []
        obj = _parse_bird_json(raw)
        return bird_utils.extract_bird_items(obj)
    except Exception:
        return []


def bird_following(*, n: int = 30, timeout_s: int = 35) -> List[Dict[str, Any]]:
    raw = _run_bird(["bird", "home", "--following", "-n", str(n), "--json", "--quote-depth", "1"], timeout_s=timeout_s)
    if _detect_auth_error(raw):
        raise RuntimeError("bird_auth_missing")
    obj = _parse_bird_json(raw)
    if obj is None:
        raise RuntimeError("bird_json_invalid")
    return bird_utils.extract_bird_items(obj)


__all__ = ["bird_search", "bird_following"]
