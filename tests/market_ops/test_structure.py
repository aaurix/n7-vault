import importlib.util


def test_output_whatsapp_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.whatsapp") is not None


def test_render_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.render") is None


def test_output_summary_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.summary") is not None


def test_summary_render_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.summary_render") is None
