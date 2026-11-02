# tests/unit/test_tool_registry.py
import pytest

from app.tools.base import Evidence, ToolResult, ToolSpec
from app.tools.registry import ToolRegistry


class EchoTool:
    spec = ToolSpec(
        name="echo",
        description="回声测试工具",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    )

    def run(self, arguments: dict) -> ToolResult:
        return ToolResult(text=arguments.get("text", ""), evidence=[])


def test_register_and_get():
    reg = ToolRegistry()
    tool = EchoTool()
    reg.register(tool)
    assert reg.get("echo") is tool
    assert reg.names() == ["echo"]


def test_duplicate_name_rejected():
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError, match="echo"):
        reg.register(EchoTool())


def test_get_unknown_returns_none():
    assert ToolRegistry().get("nope") is None


def test_openai_tools_format():
    reg = ToolRegistry()
    reg.register(EchoTool())
    tools = reg.openai_tools()
    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "echo",
                "description": "回声测试工具",
                "parameters": EchoTool().spec.parameters,
            },
        }
    ]


def test_tool_protocol_runtime_checkable():
    from app.tools.base import Tool

    assert isinstance(EchoTool(), Tool)


def test_evidence_model():
    e = Evidence(source="a.md", text="片段")
    assert e.source == "a.md"
