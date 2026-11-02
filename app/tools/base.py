# app/tools/base.py
"""工具层基座：Tool Protocol + 规格/结果模型。

约定：
- Tool.run 内部 catch 全部异常，失败降级为失败文本 ToolResult，循环层永不因工具崩溃
- Evidence 不编号，全局 [n] 编号由 AgentPipeline 循环层统一分配
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class Evidence(BaseModel):
    """一条可引用证据：知识库切片（source=文档名）或联网结果（source=URL）。"""

    source: str
    text: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    text: str
    evidence: list[Evidence] = field(default_factory=list)


@runtime_checkable
class Tool(Protocol):
    spec: ToolSpec

    def run(self, arguments: dict[str, Any]) -> ToolResult: ...
