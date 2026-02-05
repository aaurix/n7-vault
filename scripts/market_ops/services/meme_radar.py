#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meme radar integration for the hourly pipeline."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, List, Optional

from ..shared.filters import BASE58_RE, EVM_ADDR_RE
from ..models import PipelineContext
from .diagnostics import measure
from .meme_radar_engine import run_meme_radar


_EXECUTOR = ThreadPoolExecutor(max_workers=1)


def _persist_radar(ctx: PipelineContext, data: Dict[str, Any]) -> None:
    try:
        path = ctx.state.meme_radar_output_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return None


def spawn_meme_radar(ctx: PipelineContext) -> Optional[Future[Dict[str, Any]]]:
    try:
        return _EXECUTOR.submit(
            run_meme_radar,
            ctx=ctx,
            hours=2,
            chains=["solana", "bsc", "base"],
            tweet_limit=120,
            limit=8,
        )
    except Exception as e:
        ctx.errors.append(f"meme_radar_spawn_failed:{e}")
        return None


def wait_meme_radar(ctx: PipelineContext, proc: Optional[Future[Dict[str, Any]]]) -> None:
    done = measure(ctx.perf, "meme_radar")
    try:
        result: Optional[Dict[str, Any]] = None
        if proc is not None:
            timeout_s = min(170.0, max(5.0, ctx.budget.remaining_s() - 8.0))
            try:
                result = proc.result(timeout=timeout_s)
            except TimeoutError:
                ctx.errors.append("meme_radar_timeout")
            except Exception as e:
                ctx.errors.append(f"meme_radar_failed:{type(e).__name__}:{e}")

        if isinstance(result, dict):
            errors = result.pop("_errors", None)
            if errors:
                ctx.errors.extend(errors)
            ctx.radar = result
            _persist_radar(ctx, result)
    finally:
        if not ctx.radar:
            ctx.radar = ctx.state.load_meme_radar_output(ctx.errors)
        ctx.radar_items = list(ctx.radar.get("items") or [])
        done()


def merge_tg_addr_candidates_into_radar(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "tg_addr_to_radar")
    resolver = ctx.resolver
    dex = ctx.dex

    addr_counts: Dict[str, int] = {}
    addr_examples: Dict[str, str] = {}

    texts = [t for t in ctx.human_texts if t]
    if len(texts) > 500:
        addr_texts: List[str] = []
        other_texts: List[str] = []
        for t in texts:
            if EVM_ADDR_RE.search(t) or BASE58_RE.search(t):
                addr_texts.append(t)
            else:
                other_texts.append(t)
        texts = (addr_texts + other_texts)[:500]

    for t in texts:
        _syms, addrs = resolver.extract_symbols_and_addrs(t, require_sol_digit=True)
        seen_msg = set()
        for a in addrs:
            if a in seen_msg:
                continue
            seen_msg.add(a)
            addr_counts[a] = addr_counts.get(a, 0) + 1
            addr_examples.setdefault(a, t[:220])

    tg_addr_items: List[Dict[str, Any]] = []
    dex_cache: Dict[str, Dict[str, Any] | None] = {}
    for addr, cnt in sorted(addr_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]:
        if addr in dex_cache:
            dexm = dex_cache[addr]
        else:
            dexm = dex.enrich_addr(addr)
            dex_cache[addr] = dexm
        if not dexm:
            continue
        tg_addr_items.append(
            {
                "addr": addr,
                "mentions": cnt,
                "tickers": [dexm.get("baseSymbol")] if dexm.get("baseSymbol") else [],
                "examples": [{"handle": "TG", "text": addr_examples.get(addr, "")[:220]}],
                "dex": dexm,
                "sourceKey": f"TG:{addr}",
            }
        )

    seen_addr = {str(it.get("addr") or "") for it in ctx.radar_items}
    for it in tg_addr_items:
        a = str(it.get("addr") or "")
        if a and a not in seen_addr:
            ctx.radar_items.append(it)
            seen_addr.add(a)

    done()
