#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram ingestion and viewpoint extraction."""

from __future__ import annotations

from typing import Any, Dict, List

from ..bots import load_bot_sender_ids
from ..config import TG_CHANNELS, VIEWPOINT_CHAT_IDS
from ..filters import is_botish_text
from ..models import PipelineContext
from ..tg_client import msg_text, sender_id
from ..viewpoints import extract_viewpoint_threads
from .pipeline_timing import measure


def require_tg_health(ctx: PipelineContext) -> None:
    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")


def fetch_tg_messages(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "tg_fetch_and_replay")

    since = ctx.since
    until = ctx.until

    # formula feed
    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    formula_msgs = ctx.client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    if not formula_msgs:
        try:
            ctx.client.replay(int(formula_id), limit=400, since=since, until=until)
        except Exception as e:
            ctx.errors.append(f"formula_replay_failed:{e}")
        formula_msgs = ctx.client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    ctx.messages_by_chat[formula_id] = formula_msgs

    # viewpoint chats
    for cid in sorted(VIEWPOINT_CHAT_IDS):
        s = str(cid)
        rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until)
        if not rows:
            try:
                ctx.client.replay(cid, limit=300, since=since, until=until)
            except Exception:
                pass
            rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until)
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
            out.append(t[:360])

    ctx.human_texts = out
    ctx.perf["viewpoint_threads_msgs_in"] = float(len(out))

    done()


def build_viewpoint_threads(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "viewpoint_threads")
    import time

    t0 = time.perf_counter()
    vp = extract_viewpoint_threads(ctx.human_texts, min_heat=3, weak_heat=1)
    ctx.perf["viewpoint_threads_extract"] = round(time.perf_counter() - t0, 3)
    ctx.strong_threads = list(vp.get("strong") or [])
    ctx.weak_threads = list(vp.get("weak") or [])
    done()
