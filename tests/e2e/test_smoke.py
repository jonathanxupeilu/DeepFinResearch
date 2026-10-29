import os

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("DEEPSEEK_API_KEY") or not os.getenv("DASHSCOPE_API_KEY"),
        reason="需要真实 API Key，设置后运行: pytest tests/e2e -m e2e",
    ),
]


def test_full_rag_roundtrip(tmp_path, monkeypatch):
    """入库 → 检索 → 问答 全链路冒烟（真实 Chroma + 真实 API）。"""
    from app.config import get_settings
    from app.ingest.indexer import Indexer
    from app.models import Document
    from app.retrieval.store import VectorStore

    monkeypatch.setenv("CHROMA_DIR", str(tmp_path))  # 隔离默认 chroma 目录
    get_settings.cache_clear()  # 防 lru_cache 带入其他测试的假配置（参考 test_factory）
    s = get_settings()
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="smoke")
    from app.llm.client import DeepSeekClient
    from app.llm.embedding import DashScopeEmbedder

    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    idx = Indexer(store, embedder, s.chunk_size, s.chunk_overlap)
    result = idx.index_document(
        Document(
            source="测试.md", content="巴菲特的护城河理论指企业拥有的可持续竞争优势。"
        )
    )
    assert result.added > 0

    from app.pipeline.rag import RAGPipeline
    from app.retrieval.retriever import Retriever

    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    answer = RAGPipeline(retriever, llm).answer("什么是护城河理论？")
    assert answer.answer
    assert len(answer.citations) >= 1
    get_settings.cache_clear()  # teardown 恢复，避免污染后续测试
