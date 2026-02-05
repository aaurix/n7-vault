import importlib.util


def test_output_whatsapp_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.whatsapp") is not None


def test_render_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.render") is None


def test_output_summary_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.summary") is not None


def test_summary_render_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.summary_render") is None


def test_shared_filters_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.shared.filters") is not None


def test_filters_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.filters") is None


def test_oi_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.oi.service") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.oi.plan") is not None


def test_oi_legacy_modules_removed():
    assert importlib.util.find_spec("scripts.market_ops.oi") is None
    assert importlib.util.find_spec("scripts.market_ops.services.oi_service") is None
    assert importlib.util.find_spec("scripts.market_ops.oi_plan_pipeline") is None


def test_topics_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.topics.pipeline") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.tg") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.twitter") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.fallback") is not None


def test_topics_legacy_modules_removed():
    assert importlib.util.find_spec("scripts.market_ops.topic_pipeline") is None
    assert importlib.util.find_spec("scripts.market_ops.tg_topics_fallback") is None
    assert importlib.util.find_spec("scripts.market_ops.services.tg_topics") is None
    assert importlib.util.find_spec("scripts.market_ops.services.twitter_topics") is None
