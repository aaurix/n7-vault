#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OpenAI embeddings helper (with lightweight cache)."""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request as urlreq
from typing import Dict, List, Optional, Sequence

from ..utils.paths import repo_root

from .keys import load_openai_api_key


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def _default_embed_cache_path() -> str:
    return str(repo_root() / "state" / "embeddings_cache.json")


_EMBED_CACHE: Optional[Dict[str, List[float]]] = None
_EMBED_CACHE_PATH: Optional[str] = None
_EMBED_DIRTY: bool = False


def _load_embed_cache(path: str) -> Dict[str, List[float]]:
    try:
        if os.path.exists(path):
            data = json.loads(open(path, "r", encoding="utf-8").read())
            if isinstance(data, dict):
                out: Dict[str, List[float]] = {}
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, list):
                        out[k] = [float(x) for x in v]
                return out
    except Exception:
        pass
    return {}


def _save_embed_cache(path: str, cache: Dict[str, List[float]], *, max_items: int = 5000) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # naive prune: keep most-recent by insertion order is not tracked; just cap by arbitrary slice
        if len(cache) > max_items:
            keys = list(cache.keys())[-max_items:]
            cache = {k: cache[k] for k in keys}
        open(path, "w", encoding="utf-8").write(json.dumps(cache, ensure_ascii=False))
    except Exception:
        pass


def flush_embeddings_cache() -> None:
    """Best-effort flush to disk (optional)."""

    global _EMBED_DIRTY
    if not _EMBED_DIRTY:
        return
    if _EMBED_CACHE is None or not _EMBED_CACHE_PATH:
        return
    _save_embed_cache(_EMBED_CACHE_PATH, _EMBED_CACHE)
    _EMBED_DIRTY = False


def embeddings(
    *,
    texts: Sequence[str],
    model: str = "text-embedding-3-small",
    timeout: int = 30,
    cache_path: Optional[str] = None,
) -> List[List[float]]:
    """Embedding with disk cache keyed by sha1(text).

    Cache is best-effort. On any cache error, falls back to direct API call.
    Uses an in-process singleton cache to avoid reloading the JSON file multiple times per run.
    """

    global _EMBED_CACHE, _EMBED_CACHE_PATH, _EMBED_DIRTY

    api_key = load_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found")

    cache_path = cache_path or _default_embed_cache_path()
    if _EMBED_CACHE is None or _EMBED_CACHE_PATH != cache_path:
        _EMBED_CACHE_PATH = cache_path
        _EMBED_CACHE = _load_embed_cache(cache_path)
        _EMBED_DIRTY = False

    cache = _EMBED_CACHE or {}

    # Resolve cached vectors
    keys = [_sha1(t) for t in texts]
    out: List[Optional[List[float]]] = [None] * len(keys)
    missing_idx: List[int] = []
    missing_texts: List[str] = []

    for i, k in enumerate(keys):
        if k in cache:
            out[i] = cache[k]
        else:
            missing_idx.append(i)
            missing_texts.append(texts[i])

    # Fetch only missing
    if missing_texts:
        payload = {"model": model, "input": list(missing_texts)}

        req = urlreq.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "clawdbot-hourly/1.0",
            },
            method="POST",
        )

        with urlreq.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        vecs: List[List[float]] = []
        for row in (data.get("data") or []):
            v = row.get("embedding")
            if isinstance(v, list):
                vecs.append([float(x) for x in v])

        # Fill outputs + write-through cache
        for j, i in enumerate(missing_idx):
            if j < len(vecs):
                out[i] = vecs[j]
                cache[keys[i]] = vecs[j]
                _EMBED_DIRTY = True

        # write-through (best-effort)
        flush_embeddings_cache()

    # Persist the singleton back
    _EMBED_CACHE = cache

    return [v or [] for v in out]


__all__ = ["embeddings", "flush_embeddings_cache"]
