#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Summary/render helpers for Twitter/X following analysis."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..filters import extract_symbols_and_addrs


_ALLOWED_SENTIMENTS = ("偏多", "偏空", "分歧", "中性")

_BULL_KWS = [
    "bull",
    "long",
    "buy",
    "pump",
    "moon",
    "看多",
    "做多",
    "上涨",
    "突破",
    "拉盘",
]

_BEAR_KWS = [
    "bear",
    "short",
    "sell",
    "dump",
    "rug",
    "看空",
    "做空",
    "下跌",
    "破位",
    "砸盘",
]

_NARRATIVE_PATTERNS: List[Dict[str, Any]] = [
    {"label": "突破/新高", "kws": ["breakout", "突破", "新高", "ath", "新高点", "突破位"]},
    {"label": "回调/走弱", "kws": ["回调", "下跌", "走弱", "砸盘", "dump", "selloff"]},
    {"label": "多头升温", "kws": ["bull", "long", "做多", "看多", "pump", "moon"]},
    {"label": "空头升温", "kws": ["bear", "short", "做空", "看空", "砸盘", "rug"]},
    {"label": "资金流入/热度升温", "kws": ["inflow", "资金流入", "热度", "volume", "成交放大", "买盘"]},
    {"label": "资金流出/热度降温", "kws": ["outflow", "资金流出", "降温", "抛压", "卖压"]},
]

_EVENT_PATTERNS: List[Dict[str, Any]] = [
    {"label": "上所/上架", "kws": ["上线", "上所", "上架", "list", "listing", "binance", "coinbase", "okx", "bybit"]},
    {"label": "解锁/释放", "kws": ["unlock", "解锁", "释放", "vesting"]},
    {"label": "黑客/安全", "kws": ["hack", "exploit", "漏洞", "被盗", "攻击", "黑客"]},
    {"label": "清算/爆仓", "kws": ["liquidation", "清算", "爆仓"]},
    {"label": "监管/诉讼", "kws": ["sec", "监管", "诉讼", "court", "delist", "下架"]},
    {"label": "融资/投资", "kws": ["融资", "投资", "funding", "raise", "round"]},
    {"label": "空投/激励", "kws": ["airdrop", "空投", "激励", "points", "积分"]},
    {"label": "回购/销毁", "kws": ["buyback", "回购", "销毁", "burn"]},
    {"label": "合作/集成", "kws": ["合作", "partner", "partnership", "integrate", "integration"]},
    {"label": "脱锚/稳定币", "kws": ["depeg", "脱锚", "peg", "稳定币"]},
]

_SYMBOL_RE = re.compile(r"\$[A-Za-z0-9]{2,10}")
_MAJOR_SYMS = {
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "DOGE",
    "AVAX",
    "OP",
    "ARB",
    "SUI",
    "SEI",
    "APT",
}
_MAJOR_RE = re.compile(r"\b(?:" + "|".join(sorted(_MAJOR_SYMS)) + r")\b", re.IGNORECASE)


def _guess_sentiment(snippets: List[str]) -> str:
    bull = 0
    bear = 0
    for s in snippets:
        low = s.lower()
        if any(k in low for k in _BULL_KWS):
            bull += 1
        if any(k in low for k in _BEAR_KWS):
            bear += 1
    if bull and bear:
        if bull >= bear * 1.5:
            return "偏多"
        if bear >= bull * 1.5:
            return "偏空"
        return "分歧"
    if bull:
        return "偏多"
    if bear:
        return "偏空"
    return "中性"


def _extract_symbol_hint(text: str) -> str:
    m = _SYMBOL_RE.search(text or "")
    if not m:
        return ""
    return m.group(0)[1:].upper()


def _extract_symbols(text: str, *, resolver: Optional[Any] = None) -> List[str]:
    syms: List[str] = []
    if resolver is not None:
        try:
            syms, _addrs = resolver.extract_symbols_and_addrs(text or "")
        except Exception:
            syms = []
    if not syms:
        syms, _addrs = extract_symbols_and_addrs(text or "")
    majors = [x.upper() for x in _MAJOR_RE.findall(text or "")]
    for sym in majors:
        if sym and sym not in syms:
            syms.append(sym)
    return syms


def _pick_symbol(text: str, *, resolver: Optional[Any] = None) -> str:
    syms = _extract_symbols(text, resolver=resolver)
    if syms:
        return str(syms[0])
    return _extract_symbol_hint(text)


def _event_label(text: str) -> str:
    low = (text or "").lower()
    for pat in _EVENT_PATTERNS:
        if any(k in low for k in pat["kws"]):
            return str(pat["label"])
    return ""


def _has_anchor(text: str, *, resolver: Optional[Any] = None) -> bool:
    return bool(_pick_symbol(text, resolver=resolver) or _event_label(text))


def _narrative_hint(text: str, *, resolver: Optional[Any] = None) -> str:
    low = (text or "").lower()
    sym = _pick_symbol(text, resolver=resolver)
    for pat in _NARRATIVE_PATTERNS:
        if any(k in low for k in pat["kws"]):
            label = str(pat["label"])
            return f"{sym}{label}" if sym else label
    return ""


def _detect_events_from_items(
    items: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    resolver: Optional[Any] = None,
) -> List[str]:
    scored: List[Tuple[int, int, str]] = []
    for idx, it in enumerate(items):
        text = str(it.get("text") or it.get("snippet") or "")
        label = _event_label(text)
        if not label:
            continue
        sym = _pick_symbol(text, resolver=resolver)
        ev = f"{sym}{label}" if sym else f"{label}相关讨论"
        score = int(it.get("_cluster_size") or 1)
        scored.append((score, idx, ev))
    out: List[str] = []
    for _score, _idx, ev in sorted(scored, key=lambda x: (-x[0], x[1])):
        if ev in out:
            continue
        out.append(ev)
        if len(out) >= max_items:
            break
    return out


def _pick_narratives(snippets: List[str], *, max_items: int = 3) -> List[str]:
    out: List[str] = []
    for s in snippets:
        s = str(s).strip().lstrip("- ")
        if not s:
            continue
        if len(s) > 50:
            s = s[:50]
        if s in out:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _extract_narratives_from_items(
    items: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    resolver: Optional[Any] = None,
) -> List[str]:
    out: List[str] = []
    for it in items:
        text = str(it.get("text") or it.get("snippet") or "")
        hint = _narrative_hint(text, resolver=resolver)
        if not hint:
            continue
        if hint in out:
            continue
        out.append(hint)
        if len(out) >= max_items:
            break
    return out


def _normalize_list(val: Any, *, max_items: int = 3) -> List[str]:
    items: List[str] = []
    if isinstance(val, list):
        items = [str(x) for x in val]
    elif isinstance(val, str):
        items = [val]
    out: List[str] = []
    for it in items:
        s = str(it).strip().lstrip("- ")
        if not s:
            continue
        if len(s) > 80:
            s = s[:80]
        if s in out:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_sentiment(val: Any, *, fallback: str) -> str:
    s = str(val or "").strip()
    if not s:
        return fallback
    if any(tag in s for tag in _ALLOWED_SENTIMENTS):
        return s[:40]
    return fallback


def _fallback_summary(
    *,
    items: List[Dict[str, Any]],
    snippets: List[str],
    total: int,
    kept: int,
    clusters: int,
    metrics: Optional[Dict[str, Any]] = None,
    resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    rep_texts = [str(it.get("text") or it.get("snippet") or "") for it in items]
    rep_texts = [t for t in rep_texts if t]
    narratives = _extract_narratives_from_items(items, max_items=3, resolver=resolver)
    if not narratives:
        narratives = _pick_narratives(rep_texts or snippets, max_items=3)
    events = _detect_events_from_items(items, max_items=3, resolver=resolver)
    if not events:
        events = _detect_events_from_items(
            [{"text": s, "_cluster_size": 1} for s in (rep_texts or snippets)],
            max_items=3,
            resolver=resolver,
        )
    meta = {"total": total, "kept": kept, "clusters": clusters}
    if metrics:
        meta["metrics"] = metrics
    return {
        "narratives": narratives,
        "sentiment": _guess_sentiment(rep_texts or snippets),
        "events": events,
        "meta": meta,
    }


def _filter_anchor_items(items: List[str], *, resolver: Optional[Any] = None) -> List[str]:
    anchored = [it for it in items if _has_anchor(it, resolver=resolver)]
    return anchored or items


def _merge_lists(primary: List[str], fallback: List[str], *, max_items: int = 3) -> List[str]:
    out: List[str] = []
    for seq in (primary, fallback):
        for it in seq:
            s = str(it).strip().lstrip("- ")
            if not s:
                continue
            if s in out:
                continue
            out.append(s)
            if len(out) >= max_items:
                return out
    return out


def _norm_compare_text(text: str) -> str:
    t = re.sub(r"[\s\W_]+", "", str(text or "").lower())
    return t


def _sentiment_tag(val: str) -> str:
    s = str(val or "")
    for tag in _ALLOWED_SENTIMENTS:
        if tag in s:
            return tag
    return ""


def _compare_lists(base: List[str], other: List[str]) -> Dict[str, Any]:
    base_keys = {_norm_compare_text(x) for x in base if _norm_compare_text(x)}
    other_keys = {_norm_compare_text(x) for x in other if _norm_compare_text(x)}
    only_base = [x for x in base if _norm_compare_text(x) not in other_keys]
    only_other = [x for x in other if _norm_compare_text(x) not in base_keys]
    overlap = [x for x in base if _norm_compare_text(x) in other_keys]
    return {
        "only_base": only_base[:3],
        "only_other": only_other[:3],
        "overlap": overlap[:3],
        "base_count": len(base),
        "other_count": len(other),
    }


def _compare_summaries(fallback: Dict[str, Any], agent: Dict[str, Any]) -> Dict[str, Any]:
    base_n = _normalize_list(fallback.get("narratives"), max_items=6)
    base_e = _normalize_list(fallback.get("events"), max_items=6)
    agent_n = _normalize_list(agent.get("narratives"), max_items=6)
    agent_e = _normalize_list(agent.get("events"), max_items=6)
    base_s = str(fallback.get("sentiment") or "")
    agent_s = str(agent.get("sentiment") or "")
    return {
        "sentiment_base": base_s,
        "sentiment_agent": agent_s,
        "sentiment_match": _sentiment_tag(base_s) == _sentiment_tag(agent_s),
        "narratives": _compare_lists(base_n, agent_n),
        "events": _compare_lists(base_e, agent_e),
    }


def _merge_summary(
    *,
    fallback: Dict[str, Any],
    agent: Dict[str, Any],
    resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    base_n = _normalize_list(fallback.get("narratives"), max_items=6)
    base_e = _normalize_list(fallback.get("events"), max_items=6)
    agent_n = _filter_anchor_items(_normalize_list(agent.get("narratives"), max_items=6), resolver=resolver)
    agent_e = _filter_anchor_items(_normalize_list(agent.get("events"), max_items=6), resolver=resolver)
    return {
        "narratives": _merge_lists(agent_n, base_n, max_items=3),
        "sentiment": _normalize_sentiment(agent.get("sentiment"), fallback=str(fallback.get("sentiment") or "中性")),
        "events": _merge_lists(agent_e, base_e, max_items=3),
        "meta": fallback.get("meta") or {},
    }
