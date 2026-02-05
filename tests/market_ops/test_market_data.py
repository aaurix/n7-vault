from market_ops.ports.market_data import fetch_dex_market


class DummyDex:
    def enrich_addr(self, addr):
        return {"price": 1}


def test_fetch_dex_market():
    out = fetch_dex_market("0x1", "SYM", dex=DummyDex())
    assert out["price"] == 1
