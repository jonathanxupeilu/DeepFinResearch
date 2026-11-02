# tests/unit/test_models.py
import pytest
from pydantic import ValidationError

from app.models import Chunk, Citation, Document, RagAnswer, RetrievedChunk, TraceStep


def test_chunk_creation():
    c = Chunk(doc_id="d1", source="a.md", chunk_index=0, text="内容")
    assert c.text == "内容"


def test_chunk_rejects_empty_text():
    with pytest.raises(ValidationError):
        Chunk(doc_id="d1", source="a.md", chunk_index=0, text="  ")


def test_retrieved_chunk_has_score():
    c = RetrievedChunk(doc_id="d1", source="a.md", chunk_index=0, text="x", score=0.87)
    assert c.score == 0.87


def test_citation_fields():
    c = Citation(marker=1, source="a.md", text="片段")
    assert c.marker == 1


def test_document_auto_doc_id():
    d = Document(source="a.md", content="全文内容")
    assert len(d.doc_id) == 16
    d2 = Document(source="a.md", content="全文内容")
    assert d.doc_id == d2.doc_id  # 相同内容 → 相同 hash


def test_rag_answer_default_citations():
    a = RagAnswer(answer="回复")
    assert a.citations == []


def test_trace_step_fields():
    t = TraceStep(
        step=1,
        tool="knowledge_search",
        arguments={"query": "护城河"},
        observation="命中 3 条证据",
    )
    assert t.step == 1
    assert t.arguments["query"] == "护城河"


def test_rag_answer_default_trace_and_compat():
    a = RagAnswer(answer="回复")
    assert a.trace == []
    b = RagAnswer(
        answer="回复",
        trace=[TraceStep(step=1, tool="web_search", arguments={}, observation="ok")],
    )
    assert len(b.trace) == 1
