from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CachePolicy:
    fresh: bool = False
    ttl_s: int = 0

    def ttl(self) -> int:
        return 0 if self.fresh else int(self.ttl_s)


@dataclass(frozen=True)
class CacheTTLConfig:
    exchange: int = 0
    onchain: int = 0
    social: int = 0


def parse_cache_ttl(raw: str) -> CacheTTLConfig:
    if not raw:
        return CacheTTLConfig()
    out = {"exchange": 0, "onchain": 0, "social": 0}
    for part in raw.split(","):
        if not part.strip():
            continue
        k, v = part.split("=", 1)
        if k.strip() in out:
            out[k.strip()] = int(v.strip())
    return CacheTTLConfig(**out)


__all__ = ["CachePolicy", "CacheTTLConfig", "parse_cache_ttl"]
