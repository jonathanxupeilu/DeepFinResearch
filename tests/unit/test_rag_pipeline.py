# tests/unit/test_rag_pipeline.py
from unittest.mock import MagicMock

from app.models import RetrievedChunk
from app.pipeline.rag import RAGPipeline

CHUNKS = [
    RetrievedChunk(doc_id="d1", source="a.md", chunk_index=0, text="巴菲特推崇护城河理论", score=0.9),
    RetrievedChunk(doc_id="d2", source="b.md", chunk_index=3, text="施洛斯偏好低 PB 筛选", score=0.8),
]


def make_pipeline(llm_reply="根据[1]……"):
    retriever = MagicMock()
    retriever.retrieve.return_value = CHUNKS
    llm = MagicMock()
    llm.chat.return_value = llm_reply
    return RAGPipeline(retriever=retriever, llm=llm), retriever, llm


def test_build_messages_contains_context_and_markers():
    pipeline, _, _ = make_pipeline()
    messages = pipeline.build_messages("什么是护城河？", CHUNKS)
    assert messages[0]["role"] == "system"
    assert "仅依据" in messages[0]["content"]  # 强约束：仅依据上下文回答
    user = messages[1]["content"]
    assert "[1]" in user and "巴菲特推崇护城河理论" in user
    assert "[2]" in user and "什么是护城河？" in user


def test_answer_returns_citations():
    pipeline, retriever, llm = make_pipeline()
    result = pipeline.answer("什么是护城河？")
    assert result.answer == "根据[1]……"
    assert len(result.citations) == 2
    assert result.citations[0].marker == 1
    assert result.citations[0].source == "a.md"
    llm.chat.assert_called_once()


def test_answer_no_retrieval_honest_refusal():
    pipeline, retriever, llm = make_pipeline()
    retriever.retrieve.return_value = []
    result = pipeline.answer("知识库里没有的问题")
    assert "未找到" in result.answer
    assert result.citations == []
    llm.chat.assert_not_called()  # 不得调用 LLM 硬答
