
def test_market_data_imports():
    import scripts.market_data.onchain.dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
