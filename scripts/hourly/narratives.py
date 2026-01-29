#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Narrative/event extraction from viewpoint chats.

This is intentionally separate from token-thread clustering.
Narratives can exist without explicit tickers (e.g. "BSC已经死了").

We will use LLM summarization for narratives when available.
"""

from __future__ import annotations

from typing import List


def compress_messages(msgs: List[str], *, limit: int = 80) -> List[str]:
    """Dedup + cap message list for LLM input."""
    out = []
    seen = set()
    for m in msgs:
        m = (m or "").strip()
        if not m:
            continue
        k = m.lower()[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append(m[:260])
        if len(out) >= limit:
            break
    return out
