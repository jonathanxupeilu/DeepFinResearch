# tests/unit/test_embedding.py
from unittest.mock import MagicMock

import httpx
import pytest
from openai import AuthenticationError, RateLimitError
from tenacity import RetryError

from app.llm.embedding import MAX_CHARS, DashScopeEmbedder


def _status_error(cls, status_code: int):
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(status_code, request=request)
    return cls("err", response=response, body=None)


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
    client.embeddings.create.side_effect = lambda **kw: MagicMock(
        data=[MagicMock(embedding=[0.0]) for _ in kw["input"]]
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


def test_retry_only_on_retryable_errors():
    # 认证失败不可恢复：不应重试，且抛出原异常而非 RetryError
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    e._client = MagicMock()
    e._client.embeddings.create.side_effect = _status_error(AuthenticationError, 401)
    with pytest.raises(AuthenticationError):
        e.embed(["a"])
    assert e._client.embeddings.create.call_count == 1


def test_reraise_after_exhaustion():
    # 持续限流：重试耗尽后抛 RateLimitError 本身而非 tenacity.RetryError
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    e._client = MagicMock()
    e._client.embeddings.create.side_effect = _status_error(RateLimitError, 429)
    with pytest.raises(RateLimitError) as exc_info:
        e.embed(["a"])
    assert not isinstance(exc_info.value, RetryError)
    assert e._client.embeddings.create.call_count == 3
