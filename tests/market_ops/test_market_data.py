from scripts.market_data.utils.market_data_helpers import fetch_dex_market


class DummyDex:
    def enrich_addr(self, addr):
        return {"price": 1}


def test_fetch_dex_market():
    out = fetch_dex_market("0x1", "SYM", dex_client=DummyDex())
    assert out["price"] == 1

from scripts.market_ops.services.context_builder import build_context


def test_context_has_batchers():
    ctx = build_context()
    assert ctx.exchange is not None
    assert ctx.dex_batcher is not None
    assert ctx.social is not None
