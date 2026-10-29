# tests/unit/test_llm_client.py
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import RateLimitError
from tenacity import RetryError

from app.llm.client import DeepSeekClient, LLMClient


def _status_error(cls, status_code: int):
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(status_code, request=request)
    return cls("err", response=response, body=None)


def test_deepseek_satisfies_protocol():
    assert isinstance(DeepSeekClient(api_key="k", base_url="http://x", model="m"), LLMClient)


def test_chat_returns_text():
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="模型回复"))]
    c._client = MagicMock()
    c._client.chat.completions.create.return_value = resp
    assert c.chat([{"role": "user", "content": "hi"}]) == "模型回复"


def test_chat_passes_temperature():
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="x"))]
    c._client = MagicMock()
    c._client.chat.completions.create.return_value = resp
    c.chat([{"role": "user", "content": "hi"}], temperature=0.2)
    assert c._client.chat.completions.create.call_args.kwargs["temperature"] == 0.2


def test_chat_no_retry_on_non_retryable_exception():
    """不可重试异常（非限流/连接类）应立即原样抛出，不重试。"""
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    c._client = MagicMock()
    c._client.chat.completions.create.side_effect = Exception("boom")
    with pytest.raises(Exception, match="boom"):
        c.chat([{"role": "user", "content": "hi"}])
    assert c._client.chat.completions.create.call_count == 1


def test_chat_retries_on_rate_limit_and_reraises():
    """持续限流：重试 3 次后抛 RateLimitError 本身而非 tenacity.RetryError。"""
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    c._client = MagicMock()
    c._client.chat.completions.create.side_effect = _status_error(RateLimitError, 429)
    with patch("time.sleep"):  # mock 掉 tenacity 的指数退避等待
        with pytest.raises(RateLimitError) as exc_info:
            c.chat([{"role": "user", "content": "hi"}])
    assert not isinstance(exc_info.value, RetryError)
    assert c._client.chat.completions.create.call_count == 3
