# app/llm/client.py
import json
import os
from typing import Any, Protocol, runtime_checkable

from langsmith.wrappers import wrap_openai
from openai import APIConnectionError, OpenAI, RateLimitError
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

Message = dict[str, str]


class ToolCall(BaseModel):
    """LLM 请求的一次工具调用（arguments 已从 JSON 字符串解析）。"""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """带工具调用的对话响应：tool_calls 非空时 content 通常为空。"""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


@runtime_checkable
class LLMClient(Protocol):
    """LLM 对话接口抽象：三期 ReAct / 五期多 Agent 沿此扩展。"""

    def chat(self, messages: list[Message], temperature: float = 0.7) -> str: ...

    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], temperature: float = 0.3
    ) -> ChatResponse: ...


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        langsmith_api_key: str = "",
        langsmith_project: str = "",
        langsmith_endpoint: str = "",
    ) -> None:
        self.model = model
        if langsmith_api_key.strip():
            # langsmith SDK 靠环境变量自启；无 LANGSMITH_TRACING 时 wrap_openai 完全透传
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_API_KEY"] = langsmith_api_key.strip()
            if langsmith_project:
                os.environ["LANGSMITH_PROJECT"] = langsmith_project
            if langsmith_endpoint.strip():
                # 区域账号（APAC/EU）不设端点会上报到美国端点被 403 静默丢弃
                os.environ["LANGSMITH_ENDPOINT"] = langsmith_endpoint.strip()
        self._client = wrap_openai(OpenAI(api_key=api_key, base_url=base_url))

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def chat(self, messages: list[Message], temperature: float = 0.7) -> str:
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature  # type: ignore[arg-type]  # openai SDK 的消息联合类型不收 dict list，运行时兼容
        )
        return resp.choices[0].message.content or ""

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def chat_with_tools(
        self, messages: list[dict], tools: list[dict], temperature: float = 0.3
    ) -> ChatResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            tools=tools,
            tool_choice="auto",
        )  # type: ignore[call-overload]  # openai SDK 重载不收裸 dict list（messages/tools），运行时兼容
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}  # 参数非法 JSON 降级为空参，由工具层报"缺参"观察文本
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return ChatResponse(content=msg.content or "", tool_calls=calls)
