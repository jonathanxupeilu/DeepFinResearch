import pytest


def test_settings_requires_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from app.config import Settings

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.deepseek_model == "deepseek-chat"
    assert s.embedding_model == "text-embedding-v3"
    assert s.chunk_size == 500
    assert s.top_k == 5
