
def test_symbol_ca_modules_import():
    import scripts.market_ops.services.symbol_analysis as sym
    import scripts.market_ops.services.ca_analysis as ca
    assert hasattr(sym, "analyze_symbol")
    assert hasattr(ca, "analyze_ca")
