from scripts.market_ops.output.report_sections import ReportSection, render_markdown, render_richtext


def test_renderers_preserve_lines():
    sections = [
        ReportSection("标题区", ["时间: 00:00", "数据源: 市场/链上/社交"]),
        ReportSection("行情概览", ["现价: 1.23", "24h: +2%"]),
    ]
    md = render_markdown(sections)
    rt = render_richtext(sections)
    for line in ["时间: 00:00", "数据源: 市场/链上/社交", "现价: 1.23", "24h: +2%"]:
        assert line in md
        assert line in rt
    assert md.startswith("# ")
    assert rt.startswith("*")
