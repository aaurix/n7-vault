#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Market sentiment + watchlist selection."""

from __future__ import annotations

from typing import Any, List

from ..models import PipelineContext
from .actionable_normalization import _sentiment_from_actionable
from .pipeline_timing import measure


def compute_sentiment_and_watch(ctx: PipelineContext) -> None:
    done = measure(ctx.perf, "sentiment_watch")

    def _sent_score(s: Any) -> int:
        s2 = str(s or "").strip()
        if s2 == "偏多":
            return 1
        if s2 == "偏空":
            return -1
        return 0

    def _item_score(it: Any) -> int:
        if not isinstance(it, dict):
            return 0
        s = str(it.get("sentiment") or "").strip()
        if s:
            return _sent_score(s)
        buy = str(it.get("why_buy") or "").strip()
        not_buy = str(it.get("why_not_buy") or "").strip()
        return _sent_score(_sentiment_from_actionable(why_buy=buy, why_not=not_buy))

    sc = 0
    n = 0
    for it in (ctx.narratives or [])[:5]:
        sc += _item_score(it)
        n += 1
    for it in (ctx.twitter_topics or [])[:5]:
        sc += _item_score(it)
        n += 1

    sentiment = "分歧"
    if n:
        if sc >= 2:
            sentiment = "偏多"
        elif sc <= -2:
            sentiment = "偏空"
        else:
            sentiment = "分歧"

    ctx.sentiment = sentiment

    watch: List[str] = []

    # OI first
    for ln in ctx.oi_lines[:5]:
        # format: "- SYMBOL ..."
        s = (ln or "").lstrip("- ").split(" ", 1)[0].strip().upper()
        if s and s not in watch:
            watch.append(s)

    # Then TG token threads
    for s in [str(t.get("sym") or "").upper().strip() for t in (ctx.threads or []) if t.get("sym")][:6]:
        if s and s not in watch:
            watch.append(s)

    # Then pinned assets from narratives
    for it in (ctx.narratives or [])[:5]:
        asset = str(it.get("asset_name") or "").strip()
        if asset and asset not in watch:
            watch.append(asset)
        rel = it.get("related_assets")
        if isinstance(rel, list):
            for x in rel[:3]:
                xs = str(x).strip()
                if xs and xs not in watch:
                    watch.append(xs)

    ctx.watch = [x for x in watch if x][:3]
    done()
