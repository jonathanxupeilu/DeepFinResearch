"""三期 Agent 真实链路冒烟：DeepSeek function calling 格式校准 + ReAct 循环。"""

import pytest
from pydantic import ValidationError


def _has_keys() -> bool:
    try:
        from app.config import Settings

        s = Settings()
    except ValidationError:
        return False
    return bool(s.deepseek_api_key and s.dashscope_api_key)


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not _has_keys(),
        reason="需要真实 API Key（.env 或环境变量），设置后运行: pytest tests/e2e -m e2e",
    ),
]


@pytest.fixture
def agent(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.llm.client import DeepSeekClient
    from app.llm.embedding import DashScopeEmbedder
    from app.models import Document
    from app.pipeline.agent import AgentPipeline
    from app.retrieval.retriever import Retriever
    from app.retrieval.store import VectorStore
    from app.tools.knowledge_search import KnowledgeSearchTool
    from app.tools.registry import ToolRegistry

    monkeypatch.setenv("CHROMA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        s = get_settings()
        store = VectorStore(persist_dir=tmp_path / "chroma", collection="agent_smoke")
        embedder = DashScopeEmbedder(
            s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
        )
        from app.ingest.indexer import Indexer

        idx = Indexer(store, embedder, s.chunk_size, s.chunk_overlap)
        idx.index_document(
            Document(
                source="测试.md",
                content="巴菲特的护城河理论指企业拥有的可持续竞争优势，如品牌与网络效应。",
            )
        )
        retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
        llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
        registry = ToolRegistry()
        registry.register(KnowledgeSearchTool(retriever))
        yield AgentPipeline(registry, llm)
    finally:
        get_settings.cache_clear()


def test_agent_greeting_answers_without_tools(agent):
    result = agent.answer("你好")
    assert result.answer
    assert result.trace == []  # 闲聊不调工具（取代一期正则分流）


def test_agent_calls_knowledge_search_for_kb_question(agent):
    result = agent.answer("什么是护城河理论？请先调用知识库检索工具查证再回答。")
    assert result.answer
    assert any(t.tool == "knowledge_search" for t in result.trace)
    assert result.citations  # 证据编号进入引用
