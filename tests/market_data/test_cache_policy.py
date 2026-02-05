from scripts.market_data.utils.cache import CachePolicy, parse_cache_ttl


def test_parse_cache_ttl_basic():
    cfg = parse_cache_ttl("exchange=300,onchain=900,social=60")
    assert cfg.exchange == 300
    assert cfg.onchain == 900
    assert cfg.social == 60


def test_cache_policy_fresh_overrides():
    p = CachePolicy(fresh=True, ttl_s=120)
    assert p.ttl() == 0
