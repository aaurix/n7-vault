from scripts.market_ops.services.context_builder import build_context


def test_context_builds_exchange_batcher_with_ttl():
    ctx = build_context(cache_ttl="exchange=123,onchain=0,social=0")
    assert ctx.exchange.cache_policy.ttl_s == 123
    assert ctx.exchange.cache_policy.fresh is False
