
def test_adapters_import():
    import market_ops.adapters.dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
