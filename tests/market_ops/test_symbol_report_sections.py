from scripts.market_ops.output.report_sections import render_markdown, render_richtext
from scripts.market_ops.output.symbol_report import build_symbol_sections


def test_build_symbol_sections_contains_core_titles():
    prepared = {
        "prepared": {
            "symbol": "TEST",
            "price": {"now": 1.2, "chg_24h_pct": 2.0, "chg_1h_pct": 0.5, "chg_4h_pct": 1.0},
            "oi": {"chg_1h_pct": 1.0, "chg_4h_pct": 2.0, "chg_24h_pct": 3.0, "oi_value_now": 1000},
            "market": {"market_cap": 1000000, "fdv": 2000000},
            "derived": {"scores": {"trend": 70, "oi": 65, "social": 50, "overall": 60}, "bias_hint": "偏多"},
        }
    }
    dash = {"verdict": "偏多", "bullets": ["要点1"], "risks": ["风险1"]}
    sections = build_symbol_sections(prepared, dash)
    titles = [s.title for s in sections]
    assert "行情概览" in titles
    assert "评分与解释" in titles
    md = render_markdown(sections)
    rt = render_richtext(sections)
    assert "要点1" in md and "要点1" in rt


def test_render_symbol_report_dual_output():
    from scripts.market_ops.output.symbol_report import render_symbol_report

    prepared = {"prepared": {"symbol": "TEST"}}
    dash = {"verdict": "观望"}
    report = render_symbol_report(prepared, dash)
    assert report["markdown"]
    assert report["richtext"]
    assert "TEST" in report["markdown"]
    assert "TEST" in report["richtext"]
