from scripts.market_ops.features.meme_radar.engine import _detect_bird_auth_error, _normalize_candidates


def test_normalize_candidates_dedup():
    raw = [{"addr": "0x1"}, {"addr": "0x1"}, {"addr": "0x2"}]
    out = _normalize_candidates(raw)
    assert len(out) == 2


def test_detect_bird_auth_error():
    raw = "Missing auth_token - provide via --auth-token\nMissing required credentials"
    assert _detect_bird_auth_error(raw)


def test_twitter_following_render_removed():
    import importlib.util

    assert importlib.util.find_spec("scripts.market_ops.services.twitter_following_render") is None
