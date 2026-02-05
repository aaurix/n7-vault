#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OpenAI/OpenRouter helpers (chat/embeddings/parsing split)."""

from __future__ import annotations

from .keys import load_chat_api_key, load_openai_api_key, load_openrouter_api_key
from .embeddings import embeddings, flush_embeddings_cache
from .chat import (
    chat_json,
    detect_twitter_following_events,
    summarize_narratives,
    summarize_oi_trading_plans,
    summarize_overall,
    summarize_tg_actionables,
    summarize_token_thread,
    summarize_token_threads_batch,
    summarize_twitter_actionables,
    summarize_twitter_ca_viewpoints,
    summarize_twitter_following,
    summarize_twitter_topics,
)
from .parsing import parse_json_object

__all__ = [
    "load_openai_api_key",
    "load_openrouter_api_key",
    "load_chat_api_key",
    "embeddings",
    "flush_embeddings_cache",
    "parse_json_object",
    "chat_json",
    "summarize_token_thread",
    "summarize_token_threads_batch",
    "summarize_oi_trading_plans",
    "summarize_tg_actionables",
    "summarize_twitter_actionables",
    "detect_twitter_following_events",
    "summarize_twitter_following",
    "summarize_narratives",
    "summarize_twitter_topics",
    "summarize_twitter_ca_viewpoints",
    "summarize_overall",
]
