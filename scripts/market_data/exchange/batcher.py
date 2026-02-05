from __future__ import annotations

from ..utils.cache import CachePolicy
from . import provider_binance, provider_ccxt


class ExchangeBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def ohlcv(self, symbol: str, timeframe: str, limit: int, *, timeout_s: int | None = None):
        rows = provider_ccxt.fetch_ohlcv(symbol, timeframe, limit)
        if rows:
            return rows
        if timeout_s is None:
            return provider_binance.get_klines(symbol, timeframe, limit)
        return provider_binance.get_klines(symbol, timeframe, limit, timeout=timeout_s)

    def ticker_last(self, symbol: str):
        return provider_ccxt.fetch_ticker_last(symbol)

    def mark_price(self, symbol: str):
        return provider_binance.get_mark_price(symbol)

    def oi_changes(self, symbol: str):
        return provider_binance.oi_changes(symbol)

    def price_changes(self, symbol: str):
        return provider_binance.price_changes(symbol)


__all__ = ["ExchangeBatcher"]
