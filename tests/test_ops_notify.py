import importlib.util


def _safe_find_spec(module_name: str):
    try:
        return importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None


def test_pushdeer_location():
    assert _safe_find_spec("scripts.market_ops.services.notify.pushdeer") is not None
    assert _safe_find_spec("scripts.ops.notify.pushdeer") is None
