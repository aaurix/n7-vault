#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Meme radar integration for the hourly pipeline."""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional

from repo_paths import scripts_path

from ..filters import BASE58_RE, EVM_ADDR_RE
from ..models import PipelineContext
from .pipeline_timing import measure


def _meme_radar_cmd() -> List[str]:
    return [
        "python3",
        str(scripts_path("meme_radar.py")),
        "--hours",
        "2",
        "--chains",
        "solana",
        "bsc",
        "base",
        "--tweet-limit",
        "120",
        "--limit",
        "8",
    ]


def spawn_meme_radar(ctx: PipelineContext) -> Optional[subprocess.Popen[str]]:
    try:
        return subprocess.Popen(
            _meme_radar_cmd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception as e:
        ctx.errors.append(f"meme_radar_spawn_failed:{e}")
        return None


def wait_meme_radar(ctx: PipelineContext, proc: Optional[subprocess.Popen[str]]) -> None:
    done = measure(ctx.perf, "meme_radar")
    try:
        if proc is not None:
            # Keep headroom for rendering / JSON output.
            timeout_s = min(170.0, max(5.0, ctx.budget.remaining_s() - 8.0))
            try:
                proc.wait(timeout=timeout_s)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                ctx.errors.append("meme_radar_timeout")
    finally:
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
