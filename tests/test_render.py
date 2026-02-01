from __future__ import annotations

from hourly.render import split_whatsapp_text


def test_split_whatsapp_text_chunks_are_bounded() -> None:
    text = "A" * 50 + "\n" + "B" * 140
    chunks = split_whatsapp_text(text, max_chars=60)
    assert chunks
    assert all(len(c) <= 60 for c in chunks)
    assert chunks[0].startswith("A")
    assert any("B" in c for c in chunks)


def test_split_whatsapp_text_empty() -> None:
    assert split_whatsapp_text("") == []
