#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Key loading helpers for OpenAI/OpenRouter usage."""

from __future__ import annotations

import os
import re
from typing import Optional


def _load_env_key(name: str) -> Optional[str]:
    k = os.environ.get(name)
    if k:
        return k.strip()

    # Fallback for daemon-less local runs
    env_path = os.path.expanduser("~/.clawdbot/.env")
    try:
        if os.path.exists(env_path):
            raw = open(env_path, "r", encoding="utf-8").read()
            m = re.search(rf"^{re.escape(name)}\s*=\s*(.+)\s*$", raw, re.MULTILINE)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    except Exception:
        pass

    return None


def load_openai_api_key() -> Optional[str]:
    """OpenAI key (for OpenAI endpoints, embeddings, etc)."""

    return _load_env_key("OPENAI_API_KEY")


def load_openrouter_api_key() -> Optional[str]:
    """OpenRouter key (OpenAI-compatible endpoint)."""

    return _load_env_key("OPENROUTER_API_KEY")


def load_chat_api_key() -> Optional[str]:
    """Key resolver for *chat* calls (OpenRouter only).

    Chat completions are routed through OpenRouter; embeddings stay on OpenAI.
    """

    return load_openrouter_api_key()


__all__ = [
    "load_openai_api_key",
    "load_openrouter_api_key",
    "load_chat_api_key",
]
