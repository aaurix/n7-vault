#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Evidence snippet cleaning + PII stripping."""

from __future__ import annotations

import re


_PII_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+?\d[\d\-\s()]{7,}\d)")
_NOISE_RE = re.compile(
    r"(airdrop|giveaway|join\s+telegram|vip|signal|paid\s+group|link\s+in\s+bio|邀请码|私信|\bdm\b|抽奖|返佣)",
    re.IGNORECASE,
)


def _strip_pii(text: str) -> str:
    return _PII_RE.sub(" ", text or "")


def _clean_snippet_text(text: str) -> str:
    t = re.sub(r"https?://\S+", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _clean_evidence_snippet(text: str, *, max_len: int = 80) -> str:
    t = _clean_snippet_text(text)
    if not t:
        return ""
    t = _strip_pii(t)
    t = _NOISE_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 6:
        return ""
    if len(t) > max_len:
        t = t[:max_len]
    return t
