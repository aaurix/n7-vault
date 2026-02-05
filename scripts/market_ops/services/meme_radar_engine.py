#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Internal meme radar engine (no subprocess)."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence

from scripts.market_data import get_shared_dex_batcher, get_shared_social_batcher
from scripts.market_data.social import bird_utils

from ..config import SH_TZ
from ..filters import is_botish_text
from .entity_resolver import EntityResolver, get_shared_entity_resolver
from .evidence_cleaner import _clean_evidence_snippet
from .twitter_evidence import TwitterQuerySpec, twitter_evidence, twitter_evidence_for_ca


def _fetch_following_rows(*, hours: int, limit: int, now_sh: dt.datetime, timeout_s: int, social) -> List[Dict[str, Any]]:
    tweets = social.bird_following(n=limit, timeout_s=timeout_s)
    cut = now_sh - dt.timedelta(hours=hours)

    rows: List[Dict[str, Any]] = []
    for t in tweets:
        created = bird_utils.parse_bird_time(t.get("created_at") or t.get("createdAt") or t.get("time") or "")
        if not created:
            continue
        created_sh = created.astimezone(SH_TZ)
        if created_sh < cut:
            continue

        text = (t.get("full_text") or t.get("text") or t.get("content") or "").strip()
        if not text:
            continue
        user = t.get("user") if isinstance(t.get("user"), dict) else {}
        handle = (user.get("screen_name") or user.get("username") or "").strip()
        rows.append({"handle": handle, "text": text, "createdAt": created_sh.isoformat()})
        if len(rows) >= limit:
            break

    return rows


def _detect_bird_auth_error(raw: str) -> bool:
    text = (raw or "").lower()
    if not text:
        return False
    return any(
        pat in text
        for pat in [
            "missing auth_token",
            "missing ct0",
            "missing required credentials",
            "no twitter cookies found",
            "failed to read macos keychain",
        ]
    )


def _normalize_key(*, addr: str, sym: str) -> str:
    a = (addr or "").strip()
    s = (sym or "").strip()
    if a:
        key = a.lower() if a.startswith("0x") else a
        return f"addr:{key}"
    if s:
        return f"sym:{s.upper()}"
    return ""


def _merge_examples(dst: List[Dict[str, str]], incoming: Iterable[Any], *, max_items: int = 6) -> None:
    seen = {str(x.get("text") or "") for x in dst if isinstance(x, dict)}
    for ex in incoming:
        if len(dst) >= max_items:
            break
        if isinstance(ex, dict):
            text = str(ex.get("text") or "").strip()
            handle = str(ex.get("handle") or "").strip()
        else:
            text = str(ex or "").strip()
            handle = ""
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        dst.append({"handle": handle, "text": text[:220]})


def _normalize_candidates(raw: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for it in raw or []:
        if not isinstance(it, dict):
            continue
        addr = str(it.get("addr") or "").strip()
        sym = str(it.get("sym") or it.get("symbol") or "").strip()
        key = _normalize_key(addr=addr, sym=sym)
        if not key:
            continue

        cur = merged.get(key)
        if cur is None:
            cur = {
                "addr": addr,
                "sym": sym,
                "mentions": 0,
                "tickers": [],
                "examples": [],
                "sourceKey": it.get("sourceKey") or "",
            }
            merged[key] = cur

        cur["mentions"] = int(cur.get("mentions") or 0) + int(it.get("mentions") or 1)

        tickers: List[str] = list(cur.get("tickers") or [])
        for t in it.get("tickers") or []:
            tt = str(t or "").strip().upper()
            if tt and tt not in tickers:
                tickers.append(tt)
        if sym:
            su = sym.upper()
            if su not in tickers:
                tickers.append(su)
        cur["tickers"] = tickers

        examples: List[Dict[str, str]] = list(cur.get("examples") or [])
        if isinstance(it.get("examples"), list):
            _merge_examples(examples, it.get("examples") or [])
        elif it.get("example") is not None:
            _merge_examples(examples, [it.get("example")])
        cur["examples"] = examples

        if not cur.get("sourceKey") and it.get("sourceKey"):
            cur["sourceKey"] = it.get("sourceKey")

    out = list(merged.values())
    out.sort(key=lambda x: int(x.get("mentions") or 0), reverse=True)
    return out


def _examples_to_evidence(examples: List[Dict[str, str]], *, limit: int = 6) -> Dict[str, Any]:
    snippets: List[str] = []
    seen: set[str] = set()
    for ex in examples or []:
        if len(snippets) >= limit:
            break
        text = str((ex or {}).get("text") or "")
        cleaned = _clean_evidence_snippet(text, max_len=120)
        if not cleaned:
            continue
        key = cleaned.lower()[:100]
        if key in seen:
            continue
        seen.add(key)
        snippets.append(cleaned)
    return {"total": len(snippets), "kept": len(snippets), "snippets": snippets}


def _build_evidence(*, addr: str, sym: str, examples: List[Dict[str, str]], allow_search: bool) -> Dict[str, Any]:
    if allow_search:
        try:
            if addr:
                ev = twitter_evidence_for_ca(addr, sym or "")
            elif sym:
                spec = TwitterQuerySpec(topic=sym, aliases=[sym, f"${sym}"], intent="sentiment", window_hours=24, snippet_limit=6)
                ev = twitter_evidence(spec)
            else:
                ev = None
            if isinstance(ev, dict) and ev.get("kept"):
                return {"total": ev.get("total", 0), "kept": ev.get("kept", 0), "snippets": ev.get("snippets") or []}
        except Exception:
            pass
    return _examples_to_evidence(examples)


def _extract_candidates(rows: List[Dict[str, Any]], resolver: EntityResolver) -> List[Dict[str, Any]]:
    raw: List[Dict[str, Any]] = []
    for r in rows or []:
        text = str(r.get("text") or "").strip()
        if not text:
            continue
        if is_botish_text(text):
            continue
        syms, addrs = resolver.extract_symbols_and_addrs(text, require_sol_digit=True)
        example = {"handle": str(r.get("handle") or ""), "text": text[:220]}
        if addrs:
            seen_addr: set[str] = set()
            for addr in addrs:
                a = str(addr or "").strip()
                if not a or a in seen_addr:
                    continue
                seen_addr.add(a)
                raw.append({"addr": a, "mentions": 1, "examples": [example], "sourceKey": f"CA:{a}"})
            continue
        if syms:
            seen_sym: set[str] = set()
            for sym in syms:
                s = str(sym or "").strip().upper()
                if not s or s in seen_sym:
                    continue
                seen_sym.add(s)
                raw.append({"sym": s, "mentions": 1, "examples": [example], "sourceKey": f"TICKER:{s}"})
    return raw


def run_meme_radar(
    *,
    ctx=None,
    hours: int = 2,
    chains: Optional[Sequence[str]] = None,
    tweet_limit: int = 120,
    limit: int = 8,
) -> Dict[str, Any]:
    start = time.perf_counter()
    perf: Dict[str, float] = {}
    errors: List[str] = []

    now_sh = ctx.now_sh if ctx is not None else dt.datetime.now(SH_TZ)
    resolver: EntityResolver = ctx.resolver if ctx is not None else get_shared_entity_resolver()
    dex = ctx.dex if ctx is not None else get_shared_dex_batcher()
    social = ctx.social if ctx is not None else get_shared_social_batcher()

    timeout_s = 35.0
    if ctx is not None:
        timeout_s = min(35.0, max(8.0, ctx.budget.remaining_s() - 20.0))

    try:
        t0 = time.perf_counter()
        rows = _fetch_following_rows(hours=hours, limit=tweet_limit, now_sh=now_sh, timeout_s=timeout_s, social=social)
        perf["fetch_following"] = round(time.perf_counter() - t0, 3)
    except Exception as e:
        rows = []
        errors.append(f"meme_radar_fetch_failed:{type(e).__name__}:{e}")

    raw = _extract_candidates(rows, resolver)
    candidates = _normalize_candidates(raw)

    allow_search = True
    if ctx is not None and ctx.budget.over(reserve_s=60.0):
        allow_search = False

    allowed_chains = {c.lower() for c in (chains or []) if c}

    items: List[Dict[str, Any]] = []
    for cand in candidates:
        if len(items) >= limit:
            break
        if ctx is not None and ctx.budget.over(reserve_s=30.0):
            break

        addr = str(cand.get("addr") or "").strip()
        sym = str(cand.get("sym") or "").strip().upper()
        tickers = [t for t in (cand.get("tickers") or []) if isinstance(t, str)]
        examples = cand.get("examples") or []

        dexm = None
        if addr:
            dexm = dex.enrich_addr(addr)
        if dexm is None and sym:
            dexm = dex.enrich_symbol(sym)

        if dexm and allowed_chains:
            chain = str(dexm.get("chainId") or "").lower().strip()
            if chain and chain not in allowed_chains:
                continue

        if dexm:
            if not addr:
                addr = str(dexm.get("baseAddress") or "").strip()
            base_sym = str(dexm.get("baseSymbol") or "").strip().upper()
            if base_sym and base_sym not in tickers:
                tickers.append(base_sym)
            if not sym and base_sym:
                sym = base_sym

        if not addr and not sym:
            continue

        source_key = cand.get("sourceKey") or (f"TICKER:{sym}" if sym else f"CA:{addr}")
        evidence = _build_evidence(addr=addr, sym=sym, examples=examples, allow_search=allow_search)

        items.append(
            {
                "addr": addr,
                "mentions": int(cand.get("mentions") or 0),
                "tickers": tickers,
                "examples": examples,
                "dex": dexm or {},
                "sourceKey": source_key,
                "twitter_evidence": evidence,
            }
        )

    elapsed_s = round(time.perf_counter() - start, 3)
    out = {
        "generatedAt": dt.datetime.now(SH_TZ).isoformat(),
        "hours": hours,
        "items": items,
        "perf": perf,
        "elapsed_s": elapsed_s,
    }
    if errors:
        out["_errors"] = errors
    return out


__all__ = ["run_meme_radar", "_normalize_candidates", "_detect_bird_auth_error"]
