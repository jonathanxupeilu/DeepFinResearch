# tests/unit/test_knowledge_search_tool.py
from app.models import RetrievedChunk
from app.tools.knowledge_search import KnowledgeSearchTool

CHUNKS = [
    RetrievedChunk(
        doc_id="d1",
        source="a.md",
        chunk_index=0,
        text="巴菲特推崇护城河理论",
        score=0.9,
    ),
    RetrievedChunk(
        doc_id="d2",
        source="b.md",
        chunk_index=3,
        text="施洛斯偏好低 PB 筛选",
        score=0.8,
    ),
]


class FakeRetriever:
    def __init__(self, chunks=None, error=None):
        self._chunks = chunks if chunks is not None else CHUNKS
        self._error = error
        self.calls: list[str] = []

    def retrieve(self, query: str):
        self.calls.append(query)
        if self._error:
            raise self._error
        return self._chunks


def test_spec_shape():
    spec = KnowledgeSearchTool(FakeRetriever()).spec
    assert spec.name == "knowledge_search"
    assert spec.parameters["required"] == ["query"]
    assert spec.description


def test_run_maps_chunks_to_evidence():
    r = FakeRetriever()
    result = KnowledgeSearchTool(r).run({"query": "护城河"})
    assert r.calls == ["护城河"]
    assert len(result.evidence) == 2
    assert result.evidence[0].source == "a.md"
    assert "巴菲特推崇护城河理论" in result.text
    assert "b.md" in result.text


def test_run_empty_retrieval():
    result = KnowledgeSearchTool(FakeRetriever(chunks=[])).run({"query": "不存在"})
    assert result.evidence == []
    assert "未找到" in result.text


def test_run_exception_degrades():
    result = KnowledgeSearchTool(FakeRetriever(error=RuntimeError("boom"))).run(
        {"query": "x"}
    )
    assert result.evidence == []
    assert "失败" in result.text
    assert "boom" in result.text


def test_run_missing_query_degrades():
    result = KnowledgeSearchTool(FakeRetriever()).run({})
    assert result.evidence == []
    assert "query" in result.text
