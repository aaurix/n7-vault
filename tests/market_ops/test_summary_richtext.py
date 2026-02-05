from scripts.market_ops.output.whatsapp import WHATSAPP_CHUNK_MAX, build_summary


def test_build_summary_without_budget_keeps_length():
    oi_lines = ["- " + ("A" * 120)] * 20
    text = build_summary(title="T", oi_lines=oi_lines, whatsapp=True, apply_budget=False)
    assert len(text) > WHATSAPP_CHUNK_MAX
