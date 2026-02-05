from __future__ import annotations

from .exchange.batcher import ExchangeBatcher
from .onchain.batcher import DexBatcher
from .social.batcher import SocialBatcher
from .utils.cache import CachePolicy

_EXCHANGE: ExchangeBatcher | None = None
_DEX: DexBatcher | None = None
_SOCIAL: SocialBatcher | None = None


def get_shared_exchange_batcher(*, cache_policy: CachePolicy | None = None) -> ExchangeBatcher:
    global _EXCHANGE
    if _EXCHANGE is None:
        _EXCHANGE = ExchangeBatcher(cache_policy=cache_policy)
    elif cache_policy is not None:
        _EXCHANGE.cache_policy = cache_policy
    return _EXCHANGE


def get_shared_dex_batcher(*, cache_policy: CachePolicy | None = None) -> DexBatcher:
    global _DEX
    if _DEX is None:
        _DEX = DexBatcher(cache_policy=cache_policy)
    elif cache_policy is not None:
        _DEX.cache_policy = cache_policy
    return _DEX


def get_shared_social_batcher(*, cache_policy: CachePolicy | None = None) -> SocialBatcher:
    global _SOCIAL
    if _SOCIAL is None:
        _SOCIAL = SocialBatcher(cache_policy=cache_policy)
    elif cache_policy is not None:
        _SOCIAL.cache_policy = cache_policy
    return _SOCIAL


__all__ = [
    "ExchangeBatcher",
    "DexBatcher",
    "SocialBatcher",
    "CachePolicy",
    "get_shared_exchange_batcher",
    "get_shared_dex_batcher",
    "get_shared_social_batcher",
]
