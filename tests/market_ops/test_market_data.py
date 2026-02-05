from scripts.market_ops.market_data_helpers import fetch_dex_market


class DummyDex:
    def enrich_addr(self, addr):
        return {"price": 1}


def test_fetch_dex_market():
    out = fetch_dex_market("0x1", "SYM", dex_client=DummyDex())
    assert out["price"] == 1
