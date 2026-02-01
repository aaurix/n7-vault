#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic TG preprocessing for topic extraction."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..filters import BASE58_RE, EVM_ADDR_RE, TICKER_DOLLAR_RE
from .entity_resolver import EntityResolver, get_shared_entity_resolver
from .evidence_cleaner import _clean_snippet_text, _NOISE_RE


_EVENT_WORDS = [
    "上线",
    "上所",
    "上架",
    "解锁",
    "锁仓",
    "黑客",
    "被黑",
    "漏洞",
    "清算",
    "回购",
    "治理",
    "提案",
    "空投",
    "迁移",
    "分叉",
    "增发",
    "销毁",
    "停摆",
    "暂停",
    "恢复",
    "下线",
    "退市",
    "list",
    "listing",
    "unlock",
    "airdrop",
    "exploit",
    "hack",
    "liquidation",
    "buyback",
    "burn",
    "migration",
]

_EVENT_RE = re.compile("|".join(re.escape(x) for x in _EVENT_WORDS), re.IGNORECASE)
_NUMERIC_RE = re.compile(r"\d+(?:[\.,]\d+)?\s*(?:[kKmMwW]|万|亿|M|B|%)?")

_VAGUE_STARTS = (
    "某个",
    "某些",
    "一些",
    "有人",
    "用户",
    "群友",
    "大家",
    "投资者",
    "市场参与者",
)


def clean_tg_text(text: str) -> str:
    return _clean_snippet_text(text)


def _has_ca(text: str) -> bool:
    return bool(EVM_ADDR_RE.search(text) or BASE58_RE.search(text))


def _has_dollar_ticker(text: str) -> bool:
    return bool(TICKER_DOLLAR_RE.search(text))


def _has_event_word(text: str) -> bool:
    return bool(_EVENT_RE.search(text))


def _has_numeric(text: str) -> bool:
    return bool(_NUMERIC_RE.search(text))


def prefilter_tg_topic_text(text: str, *, resolver: Optional[EntityResolver] = None) -> bool:
    """Deterministic prefilter for TG topic extraction.

    Keep only messages that satisfy at least one:
    - CA
    - $TICKER
    - event word + token-like symbol
    - event word + numeric scale
    """

    t = clean_tg_text(text)
    if not t:
        return False

    resolver = resolver or get_shared_entity_resolver()
    syms, _addrs = resolver.extract_symbols_and_addrs(t)

    has_ca = _has_ca(t)
    has_dollar = _has_dollar_ticker(t)
    has_symbol = bool(syms)
    has_event = _has_event_word(t)
    has_numeric = _has_numeric(t)

    if has_ca or has_dollar:
        return True
    if has_event and (has_symbol or has_numeric):
        return True
    return False


def filter_tg_topic_texts(
    texts: List[str],
    *,
    resolver: Optional[EntityResolver] = None,
    limit: int = 200,
    max_len: int = 260,
) -> List[str]:
    resolver = resolver or get_shared_entity_resolver()
    out: List[str] = []
    seen: set[str] = set()

    for t in texts[:800]:
        cleaned = clean_tg_text(t)
        if not cleaned:
            continue
        if not prefilter_tg_topic_text(cleaned, resolver=resolver):
            continue
        key = cleaned.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned[:max_len])
        if len(out) >= limit:
            break
    return out


def score_tg_text(text: str, *, resolver: Optional[EntityResolver] = None) -> float:
    t = clean_tg_text(text)
    if not t:
        return 0.0

    resolver = resolver or get_shared_entity_resolver()
    syms, _addrs = resolver.extract_symbols_and_addrs(t)

    has_ca = _has_ca(t)
    has_dollar = _has_dollar_ticker(t)
    has_symbol = bool(syms)
    has_event = _has_event_word(t)
    has_numeric = _has_numeric(t)
    promo = bool(_NOISE_RE.search(t))

    score = 0.0
    if has_ca:
        score += 2.6
    if has_dollar:
        score += 1.8
    if has_symbol:
        score += 1.0
    if has_event:
        score += 0.8
    if has_event and has_numeric:
        score += 0.6
    if promo:
        score -= 0.6
    return max(0.0, score)


def score_tg_cluster(item: Dict[str, Any], *, resolver: Optional[EntityResolver] = None) -> float:
    """Score a clustered TG topic representative for ranking."""

    text = str(item.get("text") or "")
    base = score_tg_text(text, resolver=resolver)
    size = int(item.get("_cluster_size") or 1)
    # reward higher heat without overpowering the content score
    score = base + 0.35 * max(0, size - 1)
    return round(score, 3)


def _has_anchor(text: str, *, resolver: Optional[EntityResolver] = None) -> bool:
    t = clean_tg_text(text)
    if not t:
        return False
    resolver = resolver or get_shared_entity_resolver()
    syms, _addrs = resolver.extract_symbols_and_addrs(t)
    if _has_ca(t) or _has_dollar_ticker(t):
        return True
    if syms:
        return True
    if _has_event_word(t):
        return True
    if _has_numeric(t):
        return True
    return False


def postfilter_tg_topic_item(item: Dict[str, Any], *, resolver: Optional[EntityResolver] = None) -> bool:
    one = str(item.get("one_liner") or "").strip()
    if not one:
        return False
    if one.startswith(_VAGUE_STARTS):
        return False
    if not _has_anchor(one, resolver=resolver):
        return False
    return True


def self_check_tg_preprocess() -> Dict[str, Any]:
    samples = [
        "$ABC 上所传闻升温",
        "解锁500万，社区讨论增多",
        "今天大家都很嗨",
        "0x1234567890abcdef1234567890abcdef12345678 快速拉盘",
        "Join telegram airdrop now!!!",
    ]

    kept = [prefilter_tg_topic_text(s) for s in samples]
    scores = [score_tg_text(s) for s in samples]

    ok = bool(kept[0] and kept[1] and kept[3]) and (not kept[2])
    return {
        "ok": ok,
        "kept": kept,
        "scores": scores,
    }


__all__ = [
    "clean_tg_text",
    "filter_tg_topic_texts",
    "prefilter_tg_topic_text",
    "postfilter_tg_topic_item",
    "score_tg_cluster",
    "score_tg_text",
    "self_check_tg_preprocess",
]
