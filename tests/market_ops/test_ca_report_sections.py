from scripts.market_ops.output.ca_report import build_ca_sections
from scripts.market_ops.output.report_sections import render_markdown, render_richtext


def test_build_ca_sections_contains_core_titles():
    report = {"address": "0xabc", "symbol": "TEST", "dex": {"chainId": "eth"}}
    sections = build_ca_sections(report)
    titles = [s.title for s in sections]
    assert "行情概览" not in titles
    assert "总结" in titles
    md = render_markdown(sections)
    rt = render_richtext(sections)
    assert "0xabc" in md and "0xabc" in rt
