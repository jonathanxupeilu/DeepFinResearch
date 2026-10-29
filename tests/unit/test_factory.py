from unittest.mock import patch

import pytest

from app.factory import build_pipeline, build_ingest_components


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k2")
    from app.config import get_settings

    get_settings.cache_clear()  # 防其他测试缓存过真实 .env 内容


def test_build_pipeline_types(env):
    pipeline = build_pipeline()
    from app.pipeline.rag import RAGPipeline
    assert isinstance(pipeline, RAGPipeline)


def test_build_ingest_components(env):
    indexer = build_ingest_components()
    from app.ingest.indexer import Indexer
    assert isinstance(indexer, Indexer)
