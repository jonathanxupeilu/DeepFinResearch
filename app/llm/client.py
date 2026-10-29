# app/llm/client.py
from typing import Protocol, runtime_checkable

from openai import APIConnectionError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

Message = dict[str, str]


@runtime_checkable
class LLMClient(Protocol):
    """LLM 对话接口抽象：三期 ReAct / 五期多 Agent 沿此扩展。"""

    def chat(self, messages: list[Message], temperature: float = 0.7) -> str: ...


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

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
