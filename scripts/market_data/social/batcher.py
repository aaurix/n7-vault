from __future__ import annotations

from ..utils.cache import CachePolicy
from .provider_tg import TgClient


class SocialBatcher:
    def __init__(self, *, cache_policy: CachePolicy | None = None) -> None:
        self.cache_policy = cache_policy or CachePolicy()

    def tg_client(self) -> TgClient:
        return TgClient()


__all__ = ["SocialBatcher"]
