import importlib
from pathlib import Path


def test_scripts_package_present():
    assert importlib.util.find_spec("scripts.market_ops") is not None


def test_src_removed():
    assert not Path("src").exists()
