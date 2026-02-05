import importlib.util


def test_pushdeer_location():
    assert importlib.util.find_spec("scripts.ops.notify.pushdeer") is not None
    assert importlib.util.find_spec("scripts.pushdeer_send") is None
