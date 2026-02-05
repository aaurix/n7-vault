def test_legacy_scripts_removed():
    import importlib

    assert importlib.util.find_spec("scripts") is None
