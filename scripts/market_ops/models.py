#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data models for the hourly pipeline."""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from scripts.market_data.social.provider_tg import TgClient
    from .shared.state_manager import HourlyStateManager
    from scripts.market_data.exchange.batcher import ExchangeBatcher
    from scripts.market_data.onchain.batcher import DexBatcher
    from scripts.market_data.social.batcher import SocialBatcher
    from .shared.entity_resolver import EntityResolver


class SocialCard(TypedDict, total=False):
    source: str
    symbol: str
    symbol_type: str
    addr: str
    chain: str
    price: Optional[float]
    market_cap: Optional[float]
    fdv: Optional[float]
    sentiment: str
    one_liner: str
    signals: str
    evidence_snippets: List[str]
    drivers: List[str]
    risk: str


@dataclass(frozen=True)
class TimeBudget:
    """Deadline-based budget (monotonic)."""

    start_s: float
    deadline_s: float

    @classmethod
    def start(cls, *, total_s: float) -> "TimeBudget":
        now = time.perf_counter()
        return cls(start_s=now, deadline_s=now + float(total_s))

    def elapsed_s(self) -> float:
        return max(0.0, time.perf_counter() - self.start_s)

    def remaining_s(self) -> float:
        return max(0.0, self.deadline_s - time.perf_counter())

    def over(self, *, reserve_s: float = 0.0) -> bool:
        return time.perf_counter() >= (self.deadline_s - float(reserve_s))


@dataclass
class PipelineContext:
    now_sh: dt.datetime
    now_utc: dt.datetime
    since: str
    until: str
    hour_key: str
    use_llm: bool
    use_embeddings: bool

    client: "TgClient"
    budget: TimeBudget
    state: "HourlyStateManager"
    dex: "DexBatcher"
    resolver: "EntityResolver"
    exchange: "ExchangeBatcher"
    dex_batcher: "DexBatcher"
    social: "SocialBatcher"

    errors: List[str] = field(default_factory=list)
    llm_failures: List[str] = field(default_factory=list)
    perf: Dict[str, float] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    tg_topics_fallback_reason: str = ""

    # intermediate
    messages_by_chat: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    human_texts: List[str] = field(default_factory=list)

    oi_lines: List[str] = field(default_factory=list)
    oi_items: List[Dict[str, Any]] = field(default_factory=list)
    oi_plans: List[Dict[str, Any]] = field(default_factory=list)

    strong_threads: List[Dict[str, Any]] = field(default_factory=list)
    weak_threads: List[Dict[str, Any]] = field(default_factory=list)

    narratives: List[Dict[str, Any]] = field(default_factory=list)
    tg_actionables_attempted: bool = False

    radar: Dict[str, Any] = field(default_factory=dict)
    radar_items: List[Dict[str, Any]] = field(default_factory=list)

    twitter_topics: List[Dict[str, Any]] = field(default_factory=list)
    twitter_following: Dict[str, Any] = field(default_factory=dict)
    twitter_following_summary: Dict[str, Any] = field(default_factory=dict)
    social_cards: List[SocialCard] = field(default_factory=list)

    threads: List[Dict[str, Any]] = field(default_factory=list)

    sentiment: str = ""
    watch: List[str] = field(default_factory=list)
