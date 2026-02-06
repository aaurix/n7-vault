from __future__ import annotations


def test_ca_output_report_shape_has_no_top_level_markdown(monkeypatch):
    import scripts.market_ops.features.ca.service as ca

    class _DummyDex:
        def resolve_addr_symbol(self, addr: str) -> str:
            return ""

        def search(self, addr: str):
            return []

        def best_pair(self, pairs):
            return None

        def pair_metrics(self, pair):
            return {}

    monkeypatch.setattr(ca, "get_shared_dex_batcher", lambda: _DummyDex())
    monkeypatch.setattr(ca, "_mcporter_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(ca, "_twitter_snips_for_ca", lambda *args, **kwargs: [])

    out = ca.analyze_ca("0x" + "a" * 40, allow_llm=False)
    data = out.get("data") if isinstance(out, dict) else None
    assert isinstance(data, dict)

    assert "markdown" not in data
    assert "richtext" not in data
    assert "richtext_chunks" not in data

    report = data.get("report")
    assert isinstance(report, dict)
    assert report.get("template") == "ca"
    assert "sections" in report
    assert "markdown" in report
    assert "richtext" in report
    assert "richtext_chunks" in report
