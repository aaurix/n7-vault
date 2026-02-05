
def test_market_data_imports():
    import importlib.util

    import scripts.market_data.onchain.provider_dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
    assert importlib.util.find_spec("scripts.market_data.onchain.dexscreener") is None
