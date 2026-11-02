# tests/unit/test_llm_client.py
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import RateLimitError
from tenacity import RetryError

from app.llm.client import ChatResponse, DeepSeekClient, LLMClient, ToolCall


def _status_error(cls, status_code: int):
    request = httpx.Request("POST", "http://test")
    response = httpx.Response(status_code, request=request)
    return cls("err", response=response, body=None)


def test_deepseek_satisfies_protocol():
    assert isinstance(
        DeepSeekClient(api_key="k", base_url="http://x", model="m"), LLMClient
    )


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
    with (
        patch("time.sleep"),
        pytest.raises(RateLimitError) as exc_info,
    ):  # mock 掉退避等待
        c.chat([{"role": "user", "content": "hi"}])
    assert not isinstance(exc_info.value, RetryError)
    assert c._client.chat.completions.create.call_count == 3


def _client_with_response(message) -> DeepSeekClient:
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    resp = MagicMock()
    resp.choices = [MagicMock(message=message)]
    c._client = MagicMock()
    c._client.chat.completions.create.return_value = resp
    return c


def _fake_tool_call(id, name, arguments):  # id/name 对齐 OpenAI SDK 字段名
    # MagicMock 的 id/name 构造参数是 mock 元信息，必须显式赋值属性
    tc = MagicMock()
    tc.id = id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _tool_call_msg(
    name="knowledge_search", arguments='{"query": "护城河"}', id="call_1"
):
    return MagicMock(content=None, tool_calls=[_fake_tool_call(id, name, arguments)])


TOOLS = [{"type": "function", "function": {"name": "knowledge_search"}}]


def test_chat_with_tools_maps_tool_calls():
    c = _client_with_response(_tool_call_msg())
    resp = c.chat_with_tools([{"role": "user", "content": "查一下"}], tools=TOOLS)
    assert isinstance(resp, ChatResponse)
    assert resp.tool_calls == [
        ToolCall(id="call_1", name="knowledge_search", arguments={"query": "护城河"})
    ]
    assert resp.content == ""


def test_chat_with_tools_passes_tools_and_auto_choice():
    c = _client_with_response(_tool_call_msg())
    c.chat_with_tools([{"role": "user", "content": "x"}], tools=TOOLS)
    kwargs = c._client.chat.completions.create.call_args.kwargs
    assert kwargs["tools"] == TOOLS
    assert kwargs["tool_choice"] == "auto"


def test_chat_with_tools_plain_content_passthrough():
    c = _client_with_response(MagicMock(content="直接终答", tool_calls=None))
    resp = c.chat_with_tools([{"role": "user", "content": "你好"}], tools=TOOLS)
    assert resp.content == "直接终答"
    assert resp.tool_calls == []


def test_chat_with_tools_invalid_json_arguments_degrades_to_empty():
    c = _client_with_response(_tool_call_msg(arguments="不是JSON{"))
    resp = c.chat_with_tools([{"role": "user", "content": "x"}], tools=TOOLS)
    assert resp.tool_calls[0].arguments == {}


def test_chat_with_tools_multiple_calls():
    msg = MagicMock(
        content=None,
        tool_calls=[
            _fake_tool_call("c1", "a", "{}"),
            _fake_tool_call("c2", "b", '{"q": 1}'),
        ],
    )
    resp = _client_with_response(msg).chat_with_tools([], tools=TOOLS)
    assert [t.id for t in resp.tool_calls] == ["c1", "c2"]
    assert resp.tool_calls[1].arguments == {"q": 1}
