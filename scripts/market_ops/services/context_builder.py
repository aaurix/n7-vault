#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Context builder for the hourly pipeline."""

from __future__ import annotations

import datetime as dt

from ..config import DEFAULT_TOTAL_BUDGET_S, SH_TZ, UTC
from ..llm_openai import load_chat_api_key, load_openai_api_key
from ..models import PipelineContext, TimeBudget
from scripts.market_data import get_shared_dex_batcher, get_shared_exchange_batcher, get_shared_social_batcher
from scripts.market_data.social.provider_tg import TgClient
from scripts.market_data.onchain.provider_dexscreener import get_shared_dexscreener_client
from scripts.market_data.utils.cache import CachePolicy, parse_cache_ttl
from .entity_resolver import get_shared_entity_resolver
from .state_manager import HourlyStateManager


def _iso_z(t: dt.datetime) -> str:
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_context(
    *,
    total_budget_s: float = DEFAULT_TOTAL_BUDGET_S,
    fresh: bool = False,
    cache_ttl: str = "",
) -> PipelineContext:
    now_sh = dt.datetime.now(SH_TZ)
    now_utc = now_sh.astimezone(UTC)

    since_utc = now_utc - dt.timedelta(minutes=60)
    since = _iso_z(since_utc)
    until = _iso_z(now_utc)

    use_llm = bool(load_chat_api_key())
    use_embeddings = bool(load_openai_api_key())

    ttl_cfg = parse_cache_ttl(cache_ttl)
    exchange = get_shared_exchange_batcher(cache_policy=CachePolicy(fresh=fresh, ttl_s=ttl_cfg.exchange))
    dex_batcher = get_shared_dex_batcher(cache_policy=CachePolicy(fresh=fresh, ttl_s=ttl_cfg.onchain))
    social = get_shared_social_batcher(cache_policy=CachePolicy(fresh=fresh, ttl_s=ttl_cfg.social))

    dex = get_shared_dexscreener_client()
    resolver = get_shared_entity_resolver(dex)

    return PipelineContext(
        now_sh=now_sh,
        now_utc=now_utc,
        since=since,
        until=until,
        hour_key=now_sh.strftime("%Y-%m-%d %H:00"),
        use_llm=use_llm,
        use_embeddings=use_embeddings,
        client=TgClient(),
        budget=TimeBudget.start(total_s=total_budget_s),
        state=HourlyStateManager(),
        dex=dex,
        resolver=resolver,
        exchange=exchange,
        dex_batcher=dex_batcher,
        social=social,
    )
