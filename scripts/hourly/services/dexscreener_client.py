#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""DexScreener client with shared cache + throttle."""

from __future__ import annotations

import json
import time
import urllib.request as urlreq
from pathlib import Path
from typing import Any, Dict, List, Optional

from repo_paths import state_path


DEFAULT_TTL_S = 60 * 60
MIN_INTERVAL_S = 0.35
USER_AGENT = "clawdbot-hourly-summary/1.1"


def _default_cache_path() -> Path:
    return state_path("dexscreener_cache.json")


def _empty_cache() -> Dict[str, Any]:
    return {"version": 1, "items": {}}


def _load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return _empty_cache()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_cache()
    if not isinstance(data, dict):
        return _empty_cache()
    items = data.get("items")
    if not isinstance(items, dict):
        return _empty_cache()
    return {"version": data.get("version") or 1, "items": items}


def _cache_hit(cache: Dict[str, Any], url: str, now: float, ttl_s: int) -> Optional[Any]:
    if ttl_s <= 0:
        return None
    item = (cache.get("items") or {}).get(url)
    if not isinstance(item, dict):
        return None
    ts = float(item.get("ts") or 0)
    if not ts:
        return None
    if (now - ts) > ttl_s:
        return None
    if "data" not in item:
        return None
    return item.get("data")


def _store_cache(cache: Dict[str, Any], url: str, data: Any, now: float) -> None:
    items = cache.setdefault("items", {})
    items[url] = {"ts": now, "data": data}


def _prune_cache(cache: Dict[str, Any], *, max_items: int = 2000) -> None:
    items = cache.get("items")
    if not isinstance(items, dict):
        return
    if len(items) <= max_items:
        return
    ordered = sorted(items.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0))
    cache["items"] = dict(ordered[-max_items:])


def _save_cache(cache: Dict[str, Any], path: Path) -> None:
    try:
        _prune_cache(cache)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _fetch_json(url: str, *, timeout_s: int) -> Optional[Any]:
    try:
        req = urlreq.Request(url, headers={"User-Agent": USER_AGENT})
        with urlreq.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


class DexScreenerClient:
    def __init__(
        self,
        *,
        cache_path: Optional[Path] = None,
        ttl_s: int = DEFAULT_TTL_S,
        min_interval_s: float = MIN_INTERVAL_S,
    ) -> None:
        self.cache_path = cache_path or _default_cache_path()
        self.ttl_s = ttl_s
        self.min_interval_s = min_interval_s
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_path_loaded: Optional[Path] = None
        self._last_call_at = 0.0

    def set_cache_path(self, path: Optional[Path]) -> None:
        resolved = path or _default_cache_path()
        if self.cache_path != resolved:
            self.cache_path = resolved
            self._cache = None
            self._cache_path_loaded = None

    def _get_cache(self) -> tuple[Dict[str, Any], Path]:
        resolved = self.cache_path or _default_cache_path()
        if self._cache is not None and self._cache_path_loaded == resolved:
            return self._cache, resolved
        cache = _load_cache(resolved)
        self._cache = cache
        self._cache_path_loaded = resolved
        return cache, resolved

    def _throttle(self) -> None:
        if self.min_interval_s <= 0:
            return
        now = time.monotonic()
        if self._last_call_at <= 0:
            self._last_call_at = now
            return
        wait_s = self.min_interval_s - (now - self._last_call_at)
        if wait_s <= 0:
            self._last_call_at = now
            return
        time.sleep(wait_s)
        self._last_call_at = time.monotonic()

    def json(
        self,
        url: str,
        *,
        ttl_s: Optional[int] = None,
        timeout_s: int = 12,
        cache_path: Optional[Path] = None,
    ) -> Optional[Any]:
        if not url:
            return None
        if cache_path is not None:
            self.set_cache_path(cache_path)
        cache, path = self._get_cache()
        now = time.time()
        ttl = self.ttl_s if ttl_s is None else ttl_s
        hit = _cache_hit(cache, url, now, ttl)
        if hit is not None:
            return hit
        self._throttle()
        data = _fetch_json(url, timeout_s=timeout_s)
        if data is None:
            return None
        if ttl > 0:
            _store_cache(cache, url, data, now)
            _save_cache(cache, path)
        return data

    def search(self, q: str, *, ttl_s: Optional[int] = None) -> List[Dict[str, Any]]:
        if not q:
            return []
        url = f"https://api.dexscreener.com/latest/dex/search?q={urlreq.quote(q)}"
        data = self.json(url, ttl_s=ttl_s)
        if not isinstance(data, dict):
            return []
        pairs = data.get("pairs") or []
        return pairs if isinstance(pairs, list) else []

    @staticmethod
    def best_pair(pairs: List[Dict[str, Any]], symbol_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not pairs:
            return None
        if symbol_hint:
            hint = symbol_hint.upper()
            filtered = [p for p in pairs if ((p.get("baseToken") or {}).get("symbol") or "").upper() == hint]
            if filtered:
                pairs = filtered

        def liq(p: Dict[str, Any]) -> float:
            return float(((p.get("liquidity") or {}).get("usd") or 0) or 0)

        def vol(p: Dict[str, Any]) -> float:
            return float(((p.get("volume") or {}).get("h24") or 0) or 0)

        return sorted(pairs, key=lambda p: (liq(p), vol(p)), reverse=True)[0]

    @staticmethod
    def pair_metrics(p: Dict[str, Any]) -> Dict[str, Any]:
        if not p:
            return {}
        return {
            "chainId": p.get("chainId"),
            "dexId": p.get("dexId"),
            "url": p.get("url"),
            "pairAddress": p.get("pairAddress"),
            "baseSymbol": (p.get("baseToken") or {}).get("symbol"),
            "baseAddress": (p.get("baseToken") or {}).get("address"),
            "priceUsd": p.get("priceUsd"),
            "liquidityUsd": (p.get("liquidity") or {}).get("usd"),
            "vol24h": (p.get("volume") or {}).get("h24"),
            "chg1h": (p.get("priceChange") or {}).get("h1"),
            "chg24h": (p.get("priceChange") or {}).get("h24"),
            "fdv": p.get("fdv"),
            "marketCap": p.get("marketCap"),
        }

    def enrich_symbol(self, sym: str) -> Optional[Dict[str, Any]]:
        if not sym:
            return None
        pairs = self.search(sym)
        best = self.best_pair(pairs, symbol_hint=sym)
        if not best:
            return None
        return self.pair_metrics(best)

    def enrich_addr(self, addr: str) -> Optional[Dict[str, Any]]:
        """Resolve a contract address to best DexScreener pair metrics (best-effort)."""
        if not addr:
            return None
        pairs = self.search(addr)
        best = self.best_pair(pairs)
        if not best:
            return None
        return self.pair_metrics(best)

    def resolve_addr_symbol(self, addr: str) -> Optional[str]:
        if not addr:
            return None
        pairs = self.search(addr)
        best = self.best_pair(pairs)
        if not best:
            return None
        sym = ((best.get("baseToken") or {}).get("symbol") or "").upper().strip()
        return sym or None


_SHARED_CLIENT: Optional[DexScreenerClient] = None


def get_shared_dexscreener_client(cache_path: Optional[Path] = None) -> DexScreenerClient:
    global _SHARED_CLIENT
    if _SHARED_CLIENT is None:
        _SHARED_CLIENT = DexScreenerClient(cache_path=cache_path)
        return _SHARED_CLIENT
    if cache_path is not None:
        _SHARED_CLIENT.set_cache_path(cache_path)
    return _SHARED_CLIENT


__all__ = [
    "DexScreenerClient",
    "DEFAULT_TTL_S",
    "MIN_INTERVAL_S",
    "get_shared_dexscreener_client",
]
