#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Normalize TG actionables and provide deterministic fallbacks."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from ..shared.filters import stance_from_texts
from ..shared.entity_resolver import get_shared_entity_resolver
from ..shared.evidence_cleaner import _clean_evidence_snippet


def _sentiment_from_actionable(*, why_buy: str, why_not: str) -> str:
    if why_buy and why_not:
        return "分歧"
    if why_buy:
        return "偏多"
    if why_not:
        return "偏空"
    return "中性"


def _normalize_actionables(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resolver = get_shared_entity_resolver()
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _norm_text(val: Any, n: int) -> str:
        s = str(val or "")
        s = re.sub(r"\s+", " ", s).strip()
        return s[:n] if len(s) > n else s

    def _norm_evidence(ev: Any) -> List[str]:
        if isinstance(ev, str):
            ev_list = [x.strip() for x in re.split(r"[;；\n]", ev) if x.strip()]
        elif isinstance(ev, list):
            ev_list = [str(x).strip() for x in ev if str(x).strip()]
        else:
            ev_list = []
        cleaned: List[str] = []
        seen_ev: set[str] = set()
        for x in ev_list:
            t = _clean_evidence_snippet(x, max_len=80)
            if not t:
                continue
            k = t.lower()[:80]
            if k in seen_ev:
                continue
            seen_ev.add(k)
            cleaned.append(t)
            if len(cleaned) >= 2:
                break
        return cleaned

    for it in raw_items:
        if not isinstance(it, dict):
            continue
        asset = _norm_text(
            it.get("asset_name") or it.get("asset") or it.get("symbol") or it.get("token") or "",
            18,
        )
        why_buy = _norm_text(it.get("why_buy") or it.get("buy") or "", 42)
        why_not = _norm_text(it.get("why_not_buy") or it.get("why_not") or it.get("not_buy") or "", 42)
        trigger = _norm_text(it.get("trigger") or it.get("triggers") or "", 42)
        risk = _norm_text(it.get("risk") or it.get("risks") or "", 42)

        ev = it.get("evidence_snippets") or it.get("evidence") or it.get("snippets") or []
        ev_list = _norm_evidence(ev)

        if not asset and ev_list:
            syms, _addrs = resolver.extract_symbols_and_addrs(ev_list[0])
            if syms:
                asset = syms[0]

        asset = asset.lstrip("$").strip()
        if not asset:
            continue
        if len(asset) > 18:
            asset = asset[:18]
        if asset in seen:
            continue
        seen.add(asset)

        out.append(
            {
                "asset_name": asset,
                "why_buy": why_buy,
                "why_not_buy": why_not,
                "trigger": trigger,
                "risk": risk,
                "evidence_snippets": ev_list,
                "sentiment": _sentiment_from_actionable(why_buy=why_buy, why_not=why_not),
                "related_assets": [asset],
            }
        )

    return out


def self_check_actionables() -> Dict[str, Any]:
    """Lightweight self-check for actionable normalization (no LLM)."""

    sample_raw = [
        {
            "asset_name": "TESTCOINLONGNAMEEXCEED",
            "why_buy": "价格突破前高，资金净流入明显，交易所新增交易对，走势强势" * 2,
            "why_not_buy": "有解锁压力，社群分歧较大" * 2,
            "trigger": "突破前高并回踩确认",
            "risk": "消息噪音/情绪盘",
            "evidence_snippets": [
                "Testcoin to the moon! contact me at alpha@example.com",
                "Join telegram airdrop now!!!",
                "TEST 上所传闻升温，成交量放大",
            ],
        },
        {
            "asset": "DEMO",
            "buy": "资金关注",
            "not_buy": "",
            "trigger": "",
            "risk": "",
            "snippets": "DEMO 讨论升温；telegram群拉人",
        },
    ]

    normalized = _normalize_actionables(sample_raw)

    ok = True
    for it in normalized:
        if len(str(it.get("asset_name") or "")) > 18:
            ok = False
        for k in ["why_buy", "why_not_buy", "trigger", "risk"]:
            if len(str(it.get(k) or "")) > 42:
                ok = False
        ev = it.get("evidence_snippets") or []
        if len(ev) > 2 or any(len(str(x)) > 80 for x in ev):
            ok = False

    return {"ok": ok, "items": normalized}


def _fallback_actionables_from_texts(texts: List[str], *, limit: int = 5) -> List[Dict[str, Any]]:
    resolver = get_shared_entity_resolver()
    sym_hits: Dict[str, int] = {}
    sym_samples: Dict[str, List[str]] = {}

    for t in texts[:800]:
        syms, _addrs = resolver.extract_symbols_and_addrs(t)
        for s in syms[:2]:
            sym_hits[s] = sym_hits.get(s, 0) + 1
            sym_samples.setdefault(s, []).append(t)

    items: List[Dict[str, Any]] = []
    for sym, _cnt in sorted(sym_hits.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]:
        samples = sym_samples.get(sym, [])[:6]
        stance = stance_from_texts(samples)
        why_buy = "聊天偏多" if stance == "偏多" else ("多空分歧" if stance == "分歧" else "")
        why_not = "聊天偏空" if stance == "偏空" else ""
        ev = [_clean_evidence_snippet(s, max_len=80) for s in samples]
        ev = [x for x in ev if x]
        items.append(
            {
                "asset_name": sym,
                "why_buy": why_buy,
                "why_not_buy": why_not,
                "trigger": "关注关键位/催化",
                "risk": "消息噪音/情绪盘",
                "evidence_snippets": ev[:2],
                "sentiment": stance,
                "related_assets": [sym],
            }
        )
    return items[:limit]


def _fallback_actionables_from_radar(items: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for it in items[:25]:
        dex = it.get("dex") or {}
        sym = str(dex.get("baseSymbol") or it.get("symbol") or it.get("sym") or "").upper().strip()
        addr = str(it.get("addr") or "").strip()
        asset = sym
        if not asset and addr:
            asset = (addr[:6] + "…" + addr[-4:]) if len(addr) >= 12 else addr
        if not asset or asset in seen:
            continue
        ev = (it.get("twitter_evidence") or {}).get("snippets") or []
        ev2 = [_clean_evidence_snippet(str(s), max_len=80) for s in ev]
        ev2 = [x for x in ev2 if x][:2]
        if not ev2:
            continue
        out.append(
            {
                "asset_name": asset,
                "why_buy": "",
                "why_not_buy": "",
                "trigger": "",
                "risk": "",
                "evidence_snippets": ev2,
                "sentiment": "中性",
                "related_assets": [asset],
            }
        )
        seen.add(asset)
        if len(out) >= limit:
            break
    return out
