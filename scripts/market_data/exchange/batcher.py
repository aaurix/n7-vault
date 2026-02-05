from __future__ import annotations

from ..utils.cache import CachePolicy
from . import provider_binance, provider_ccxt


class ExchangeBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def ohlcv(self, symbol: str, timeframe: str, limit: int):
        rows = provider_ccxt.fetch_ohlcv(symbol, timeframe, limit)
        if rows:
            return rows
        return provider_binance.get_klines(symbol, timeframe, limit)


__all__ = ["ExchangeBatcher"]
