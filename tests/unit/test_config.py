import pytest


def test_settings_requires_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from app.config import Settings

    with pytest.raises(Exception):  # noqa: B017 — 仅验证缺 Key 必然报错
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


def test_settings_agent_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.tavily_api_key == ""  # 空 = 不注册 web_search
    assert s.agent_max_iterations == 5
    assert s.tavily_max_results == 5
