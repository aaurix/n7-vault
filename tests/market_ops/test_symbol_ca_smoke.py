
def test_symbol_ca_modules_import():
    import scripts.market_ops.features.symbol.service as sym
    import scripts.market_ops.features.ca.service as ca
    assert hasattr(sym, "analyze_symbol")
    assert hasattr(ca, "analyze_ca")


def test_narratives_module_removed():
    import importlib.util

    assert importlib.util.find_spec("scripts.market_ops.narratives") is None
