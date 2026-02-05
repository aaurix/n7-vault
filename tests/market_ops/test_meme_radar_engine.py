from scripts.market_ops.services.meme_radar_engine import _normalize_candidates


def test_normalize_candidates_dedup():
    raw = [{"addr": "0x1"}, {"addr": "0x1"}, {"addr": "0x2"}]
    out = _normalize_candidates(raw)
    assert len(out) == 2
