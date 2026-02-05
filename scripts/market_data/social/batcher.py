from __future__ import annotations

from ..utils.cache import CachePolicy
from . import provider_bird
from .provider_tg import TgClient


class SocialBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def tg_client(self) -> TgClient:
        return TgClient()

    def bird_search(self, query: str, *, limit: int = 30, timeout_s: int = 18):
        return provider_bird.bird_search(query, n=limit, timeout_s=timeout_s)

    def bird_following(self, n: int = 30, *, timeout_s: int = 35):
        return provider_bird.bird_following(n=n, timeout_s=timeout_s)


__all__ = ["SocialBatcher"]
