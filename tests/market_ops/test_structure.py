import importlib.util


def test_output_whatsapp_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.whatsapp") is not None


def test_render_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.render") is None
