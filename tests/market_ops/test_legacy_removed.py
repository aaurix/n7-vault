import importlib


def test_scripts_package_present():
    assert importlib.util.find_spec("scripts.market_ops") is not None
