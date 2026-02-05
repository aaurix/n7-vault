from __future__ import annotations

from ..utils.cache import CachePolicy
from . import provider_dexscreener


class DexBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def search(self, q: str):
        ttl = self.cache_policy.ttl()
        ttl_s = ttl if ttl > 0 else None
        return provider_dexscreener.dexscreener_search(q, ttl_s=ttl_s)


__all__ = ["DexBatcher"]
