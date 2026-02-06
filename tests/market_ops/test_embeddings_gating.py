from scripts.market_ops.services.context_builder import build_context


def test_context_builder_gates_embeddings_on_backend_availability(monkeypatch):
    # Even if an API key exists (for chat), embeddings should depend on the local backend.
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")

    import scripts.market_ops.services.context_builder as cb

    monkeypatch.setattr(cb, "local_embeddings_available", lambda: False)

    ctx = build_context()
    assert ctx.use_embeddings is False
