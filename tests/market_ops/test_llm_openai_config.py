import pytest


def test_resolve_chat_endpoint_uses_openai_env(monkeypatch, tmp_path):
    # Prevent reading real-user fallback env file (~/.clawdbot/.env)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "deepseek-chat")

    from scripts.market_ops.llm_openai.chat import _resolve_chat_endpoint

    base, key, model = _resolve_chat_endpoint("")
    assert base == "https://example.com/v1"
    assert key == "k-test"
    assert model == "deepseek-chat"


def test_resolve_chat_endpoint_defaults_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

    from scripts.market_ops.llm_openai.chat import _resolve_chat_endpoint

    base, _key, _model = _resolve_chat_endpoint("")
    assert base == "https://api.openai.com/v1"


def test_resolve_chat_endpoint_requires_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    from scripts.market_ops.llm_openai.chat import _resolve_chat_endpoint

    with pytest.raises(RuntimeError):
        _resolve_chat_endpoint("")
