# app/tools/registry.py
"""工具注册表：插件化注册，输出 OpenAI function calling 工具描述。"""

from typing import Any

from app.tools.base import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError(f"工具重复注册: {tool.spec.name}")
        self._tools[tool.spec.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.spec.name,
                    "description": t.spec.description,
                    "parameters": t.spec.parameters,
                },
            }
            for t in self._tools.values()
        ]
