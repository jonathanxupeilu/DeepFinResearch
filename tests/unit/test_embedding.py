# tests/unit/test_embedding.py
from unittest.mock import MagicMock

from app.llm.embedding import BATCH_SIZE, MAX_CHARS, DashScopeEmbedder


def _mock_openai(vectors: list[list[float]]) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.data = [MagicMock(embedding=v) for v in vectors]
    client.embeddings.create.return_value = resp
    return client


def test_embed_returns_vectors():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="text-embedding-v3")
    e._client = _mock_openai([[0.1, 0.2], [0.3, 0.4]])
    assert e.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_batches_over_10():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    client = MagicMock()
    # 真实 API 返回向量数与输入条数一致，mock 按输入长度回包
    client.embeddings.create.side_effect = (
        lambda **kw: MagicMock(data=[MagicMock(embedding=[0.0]) for _ in kw["input"]])
    )
    e._client = client
    out = e.embed([str(i) for i in range(25)])  # 25 条 → 3 个批次
    assert len(out) == 25
    assert e._client.embeddings.create.call_count == 3


def test_embed_truncates_overlong_text():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    e._client = _mock_openai([[0.0]])
    e.embed(["字" * (MAX_CHARS + 100)])
    sent = e._client.embeddings.create.call_args.kwargs["input"][0]
    assert len(sent) == MAX_CHARS
