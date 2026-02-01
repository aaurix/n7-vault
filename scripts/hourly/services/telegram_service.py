#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram ingestion and viewpoint extraction."""

from __future__ import annotations

from typing import Any, Dict, List

from ..bots import load_bot_sender_ids
from ..config import TG_CHANNELS, VIEWPOINT_CHAT_IDS
from ..filters import BASE58_RE, EVM_ADDR_RE, TICKER_DOLLAR_RE, is_botish_text
from ..models import PipelineContext
from ..tg_client import msg_text, sender_id
from ..viewpoints import extract_viewpoint_threads
from .pipeline_timing import measure

import os
import time


def require_tg_health(ctx: PipelineContext) -> None:
    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")


def _env_bool(name: str) -> bool:
    return os.environ.get(name) in {"1", "true", "True"}


def _tg_timeout() -> int:
    try:
        return int(os.environ.get("HOURLY_TG_TIMEOUT_S") or 12)
    except Exception:
        return 12


def _tg_total_budget() -> float:
    try:
        return float(os.environ.get("HOURLY_TG_TOTAL_BUDGET_S") or 25.0)
    except Exception:
        return 25.0


def _clip_text(text: str, *, limit: int = 360) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    # Preserve tail when CA/$TICKER appears beyond the clip window.
    if BASE58_RE.search(t[limit:]) or EVM_ADDR_RE.search(t[limit:]) or TICKER_DOLLAR_RE.search(t[limit:]):
        tail_len = min(140, max(80, limit // 3))
        tail = t[-tail_len:]
        head_len = max(0, limit - tail_len - 3)
        if head_len <= 0:
            return t[:limit]
        return f"{t[:head_len]}...{tail}"
    return t[:limit]


def fetch_tg_messages(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "tg_fetch_and_replay")

    since = ctx.since
    until = ctx.until
    timeout_s = _tg_timeout()
    budget_s = _tg_total_budget()
    disable_replay = _env_bool("HOURLY_TG_DISABLE_REPLAY")

    def budget_left(start: float) -> float:
        return max(0.0, budget_s - (time.monotonic() - start))

    start = time.monotonic()

    # formula feed
    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    if budget_left(start) <= 0:
        ctx.errors.append("tg_budget_exhausted:formula")
        done()
        return

    formula_msgs = ctx.client.fetch_messages(
        int(formula_id), limit=240, since=since, until=until, timeout=timeout_s
    )
    if not formula_msgs and not disable_replay and budget_left(start) > 3:
        try:
            ctx.client.replay(int(formula_id), limit=400, since=since, until=until, timeout=timeout_s)
        except Exception as e:
            ctx.errors.append(f"formula_replay_failed:{e}")
        formula_msgs = ctx.client.fetch_messages(
            int(formula_id), limit=240, since=since, until=until, timeout=timeout_s
        )
    ctx.messages_by_chat[formula_id] = formula_msgs

    # viewpoint chats
    for cid in sorted(VIEWPOINT_CHAT_IDS):
        if budget_left(start) <= 0:
            ctx.errors.append("tg_budget_exhausted:viewpoints")
            break
        s = str(cid)
        rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until, timeout=timeout_s)
        if not rows and not disable_replay and budget_left(start) > 3:
            try:
                ctx.client.replay(cid, limit=300, since=since, until=until, timeout=timeout_s)
            except Exception as e:
                ctx.errors.append(f"viewpoint_replay_failed:{cid}:{e}")
            rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until, timeout=timeout_s)
        ctx.messages_by_chat[s] = rows

    done()


def build_human_texts(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "human_texts")

    bot_ids = load_bot_sender_ids()
    out: List[str] = []

    for cid in VIEWPOINT_CHAT_IDS:
        for m in ctx.messages_by_chat.get(str(cid), []):
            sid = sender_id(m)
            if sid is not None and sid in bot_ids:
                continue
            t = msg_text(m)
            if not t or is_botish_text(t):
                continue
            out.append(_clip_text(t, limit=360))

    ctx.human_texts = out
    ctx.perf["viewpoint_threads_msgs_in"] = float(len(out))

    done()


def build_viewpoint_threads(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "viewpoint_threads")
    import time

    t0 = time.perf_counter()
    vp = extract_viewpoint_threads(ctx.human_texts, min_heat=3, weak_heat=1, resolver=ctx.resolver)
    ctx.perf["viewpoint_threads_extract"] = round(time.perf_counter() - t0, 3)
    ctx.strong_threads = list(vp.get("strong") or [])
    ctx.weak_threads = list(vp.get("weak") or [])
    done()
