from __future__ import annotations

from ..utils.cache import CachePolicy
from . import provider_coingecko, provider_dexscreener


class DexBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def search(self, q: str):
        ttl = self.cache_policy.ttl()
        ttl_s = ttl if ttl > 0 else None
        return provider_dexscreener.dexscreener_search(q, ttl_s=ttl_s)

    def best_pair(self, pairs, symbol_hint: str | None = None):
        return provider_dexscreener.best_pair(pairs, symbol_hint=symbol_hint)

    def pair_metrics(self, pair):
        return provider_dexscreener.pair_metrics(pair)

    def enrich_symbol(self, sym: str):
        return provider_dexscreener.enrich_symbol(sym)

    def enrich_addr(self, addr: str):
        return provider_dexscreener.enrich_addr(addr)

    def resolve_addr_symbol(self, addr: str):
        return provider_dexscreener.resolve_addr_symbol(addr)

    def market_cap_fdv(self, symbol: str):
        return provider_coingecko.get_market_cap_fdv(symbol)


__all__ = ["DexBatcher"]
