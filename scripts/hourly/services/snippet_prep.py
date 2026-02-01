#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Snippet preparation helpers for TG/Twitter evidence."""

from __future__ import annotations

from typing import Any, Dict, List

from ..filters import extract_symbols_and_addrs
from .evidence_cleaner import _clean_snippet_text


def _prep_tg_snippets(texts: List[str], *, limit: int = 120) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for t in texts[:800]:
        t = _clean_snippet_text(t)
        if not t:
            continue
        syms, addrs = extract_symbols_and_addrs(t)
        anchor = ""
        if syms:
            anchor = syms[0]
        elif addrs:
            a = addrs[0]
            anchor = (a[:6] + "…" + a[-4:]) if len(a) >= 12 else a
        if anchor and not t.startswith(anchor):
            t = f"{anchor} | {t}"
        if len(t) > 220:
            t = t[:220]
        k = t.lower()[:120]
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _prep_twitter_snippets(items: List[Dict[str, Any]], *, limit: int = 120) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for it in items[:40]:
        ev = it.get("twitter_evidence") or {}
        snippets = ev.get("snippets") or []
        dex = it.get("dex") or {}
        sym = str(dex.get("baseSymbol") or it.get("symbol") or it.get("sym") or "").upper().strip()
        addr = str(it.get("addr") or "").strip()
        anchor = sym
        if not anchor and addr:
            anchor = (addr[:6] + "…" + addr[-4:]) if len(addr) >= 12 else addr
        for s in snippets[:6]:
            t = _clean_snippet_text(str(s))
            if not t:
                continue
            if anchor and not t.startswith(anchor):
                t = f"{anchor} | {t}"
            if len(t) > 220:
                t = t[:220]
            k = t.lower()[:120]
            if k in seen:
                continue
            seen.add(k)
            out.append(t)
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    return out
