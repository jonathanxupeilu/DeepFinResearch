import pytest

from app.factory import build_ingest_components, build_pipeline


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k2")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path))  # 隔离，不写真实 data/chroma
    from app.config import get_settings

    get_settings.cache_clear()  # 防其他测试缓存过真实 .env 内容
    yield
    get_settings.cache_clear()  # teardown 恢复，避免污染后续测试


def test_build_pipeline_types(env):
    pipeline = build_pipeline()
    from app.pipeline.rag import RAGPipeline

    assert isinstance(pipeline, RAGPipeline)


def test_build_ingest_components(env):
    indexer = build_ingest_components()
    from app.ingest.indexer import Indexer

    assert isinstance(indexer, Indexer)


def test_build_monitor_runner(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k2")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path))
    monkeypatch.setenv("MONITOR_DB_PATH", str(tmp_path / "monitor.db"))
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        from app.factory import build_monitor_runner
        from app.monitor.runner import MonitorRunner

        runner = build_monitor_runner()
        assert isinstance(runner, MonitorRunner)
        assert len(runner._collectors) == 6
        (_seq, _name, file), *_ = runner._store._conn.execute("PRAGMA database_list")
        assert file == str(tmp_path / "monitor.db")
    finally:
        get_settings.cache_clear()  # teardown 恢复，避免污染后续测试
