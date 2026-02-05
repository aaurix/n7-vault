
def test_adapters_import():
    import scripts.market_ops.adapters.dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
