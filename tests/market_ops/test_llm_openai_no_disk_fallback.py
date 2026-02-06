from __future__ import annotations


def test_openai_keys_do_not_read_clawdbot_env_file(monkeypatch, tmp_path):
    """Guardrail: OPENAI_* must come from env injection, not ~/.clawdbot/.env."""

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    clawdbot_dir = tmp_path / ".clawdbot"
    clawdbot_dir.mkdir(parents=True, exist_ok=True)
    (clawdbot_dir / ".env").write_text("OPENAI_API_KEY=k-from-file\n", encoding="utf-8")

    from scripts.market_ops.llm_openai.keys import load_openai_api_key

    assert load_openai_api_key() is None

