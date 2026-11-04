# tests/unit/test_agent_pipeline.py
import json

from app.llm.client import ChatResponse, ToolCall
from app.models import TraceStep
from app.pipeline.agent import AgentPipeline
from app.pipeline.prompts import AGENT_SYSTEM_PROMPT
from app.tools.base import Evidence, ToolResult, ToolSpec
from app.tools.registry import ToolRegistry


class FakeTool:
    def __init__(self, name: str, result: ToolResult):
        self.spec = ToolSpec(
            name=name,
            description=f"{name} 描述",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        self._result = result
        self.calls: list[dict] = []

    def run(self, arguments: dict) -> ToolResult:
        self.calls.append(arguments)
        return self._result


class FakeLLM:
    """按脚本序列返回 chat_with_tools 响应；chat 为熔断兜底终答。"""

    def __init__(self, responses: list[ChatResponse], final: str = "强制终答"):
        self.responses = list(responses)
        self.final = final
        self.rounds: list[list[dict]] = []  # 每轮 chat_with_tools 收到的 messages 快照
        self.chat_messages: list[dict] | None = None

    def chat_with_tools(self, messages, tools, temperature=0.3) -> ChatResponse:
        self.rounds.append([dict(m) for m in messages])
        return self.responses.pop(0)

    def chat(self, messages, temperature=0.7) -> str:
        self.chat_messages = [dict(m) for m in messages]
        return self.final


def call(name: str, arguments: dict | None = None, id: str = "c1") -> ToolCall:
    return ToolCall(id=id, name=name, arguments=arguments or {})


def make_agent(responses, tools=None, max_iterations=5, final="强制终答"):
    registry = ToolRegistry()
    for t in tools or []:
        registry.register(t)
    llm = FakeLLM(responses, final=final)
    return AgentPipeline(registry, llm, max_iterations=max_iterations), llm, registry


def test_direct_answer_no_tools():
    agent, llm, _ = make_agent([ChatResponse(content="你好！我是投研助手")])
    result = agent.answer("你好")
    assert result.answer == "你好！我是投研助手"
    assert result.trace == []
    assert result.citations == []
    # 首轮 messages：system(静态 AGENT 提示词，时间靠 current_time 工具自主获取) + user
    assert llm.rounds[0][0] == {"role": "system", "content": AGENT_SYSTEM_PROMPT}
    assert llm.rounds[0][1]["content"] == "你好"


def test_single_tool_round_with_citations():
    kb = FakeTool(
        "knowledge_search",
        ToolResult(
            text="（来源: a.md）\n护城河内容",
            evidence=[
                Evidence(source="a.md", text="护城河内容"),
                Evidence(source="b.md", text="低PB内容"),
            ],
        ),
    )
    agent, llm, _ = make_agent(
        [
            ChatResponse(tool_calls=[call("knowledge_search", {"query": "护城河"})]),
            ChatResponse(content="依据[1]，护城河是……"),
        ],
        tools=[kb],
    )
    result = agent.answer("什么是护城河？")
    assert kb.calls == [{"query": "护城河"}]
    assert result.answer == "依据[1]，护城河是……"
    assert [c.marker for c in result.citations] == [1]
    assert result.citations[0].source == "a.md"
    # 轨迹一步
    assert result.trace == [
        TraceStep(
            step=1,
            tool="knowledge_search",
            arguments={"query": "护城河"},
            observation=result.trace[0].observation,
        )
    ]
    # 第二轮 messages 含 assistant(tool_calls) + tool 观察（带全局编号 [1][2]）
    round2 = llm.rounds[1]
    assert round2[2]["role"] == "assistant"
    assert round2[2]["tool_calls"][0]["function"]["name"] == "knowledge_search"
    tool_msg = round2[3]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "c1"
    assert "[1]（来源: a.md）" in tool_msg["content"]
    assert "[2]（来源: b.md）" in tool_msg["content"]


def test_multi_round_global_evidence_numbering():
    kb = FakeTool(
        "knowledge_search",
        ToolResult(text="x", evidence=[Evidence(source="a.md", text="e1")]),
    )
    web = FakeTool(
        "web_search",
        ToolResult(text="y", evidence=[Evidence(source="https://n.cn", text="e2")]),
    )
    agent, _, _ = make_agent(
        [
            ChatResponse(
                tool_calls=[call("knowledge_search", {"query": "q1"}, id="c1")]
            ),
            ChatResponse(tool_calls=[call("web_search", {"query": "q2"}, id="c2")]),
            ChatResponse(content="综合[1]与[2]"),
        ],
        tools=[kb, web],
    )
    result = agent.answer("对比问题")
    # 证据编号跨轮全局递增：kb=[1]，web=[2]；终答标注 [1][2] 全保留
    assert [c.marker for c in result.citations] == [1, 2]
    assert result.citations[1].source == "https://n.cn"
    assert [t.step for t in result.trace] == [1, 2]


def test_unknown_tool_name_tolerated():
    agent, llm, _ = make_agent(
        [
            ChatResponse(tool_calls=[call("nope_tool", {}, id="c1")]),
            ChatResponse(content="工具不可用，直接回答"),
        ]
    )
    result = agent.answer("x")
    assert result.answer == "工具不可用，直接回答"
    tool_msg = llm.rounds[1][3]
    assert tool_msg["role"] == "tool"
    assert "未知工具" in tool_msg["content"]
    assert result.trace[0].tool == "nope_tool"


def test_max_iterations_fuse_forces_final_answer():
    kb = FakeTool(
        "knowledge_search",
        ToolResult(text="x", evidence=[Evidence(source="a.md", text="e1")]),
    )
    endless = ChatResponse(tool_calls=[call("knowledge_search", {"query": "q"})])
    agent, llm, _ = make_agent([endless, endless], tools=[kb], max_iterations=2)
    result = agent.answer("死循环问题")
    assert result.answer == "强制终答"
    assert llm.chat_messages is not None  # 熔断后走无工具 chat
    assert len(llm.rounds) == 2  # 只允许 max_iterations 轮工具调用
    # 无 [n] 标注 → 保留全部证据
    assert [c.marker for c in result.citations] == [1, 2]


def test_tool_failure_text_passthrough():
    broken = FakeTool(
        "knowledge_search", ToolResult(text="知识库检索失败: boom", evidence=[])
    )
    agent, llm, _ = make_agent(
        [
            ChatResponse(tool_calls=[call("knowledge_search", {"query": "q"})]),
            ChatResponse(content="检索不可用，无法回答"),
        ],
        tools=[broken],
    )
    result = agent.answer("x")
    assert llm.rounds[1][3]["content"] == "知识库检索失败: boom"
    assert result.citations == []
    assert "失败" in result.trace[0].observation


def test_invalid_arguments_json_reaches_tool_as_empty():
    kb = FakeTool("knowledge_search", ToolResult(text="缺少参数", evidence=[]))
    agent, _, _ = make_agent(
        [
            ChatResponse(tool_calls=[call("knowledge_search", {})]),
            ChatResponse(content="终答"),
        ],
        tools=[kb],
    )
    agent.answer("x")
    assert kb.calls == [{}]


def test_assistant_message_arguments_serialized_as_json():
    kb = FakeTool("knowledge_search", ToolResult(text="x", evidence=[]))
    agent, llm, _ = make_agent(
        [
            ChatResponse(tool_calls=[call("knowledge_search", {"query": "中文"})]),
            ChatResponse(content="终答"),
        ],
        tools=[kb],
    )
    agent.answer("x")
    raw = llm.rounds[1][2]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(raw) == {"query": "中文"}


def test_history_injected_between_system_and_question():
    agent, llm, _ = make_agent([ChatResponse(content="结合上轮黄金板块作答")])
    history = [
        {"role": "user", "content": "最近黄金板块巨大波动的原因有哪些？"},
        {"role": "assistant", "content": "美联储、地缘、资金三方面"},
    ]
    agent.answer("我补充三个思考维度", history=history)
    msgs = llm.rounds[0]
    assert msgs[1] == {"role": "user", "content": "最近黄金板块巨大波动的原因有哪些？"}
    assert msgs[2] == {"role": "assistant", "content": "美联储、地缘、资金三方面"}
    assert msgs[3] == {"role": "user", "content": "我补充三个思考维度"}


def test_history_capped_and_content_truncated():
    agent, llm, _ = make_agent([ChatResponse(content="ok")])
    history = [{"role": "user", "content": f"q{i}"} for i in range(14)]
    history[-1]["content"] = "x" * 2000
    agent.answer("now", history=history)
    msgs = llm.rounds[0]
    assert len(msgs) == 1 + 10 + 1  # system + 最近 10 条历史 + 本轮问题
    assert msgs[1]["content"] == "q4"  # 只保留最近 10 条
    assert len(msgs[-2]["content"]) == 1500  # 超长单条被截断


def test_session_id_accepted_and_inert_without_tracing(monkeypatch):
    """观测未开启（无 LANGSMITH_TRACING）时传 session_id 不影响正常问答。"""
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    agent, _, _ = make_agent([ChatResponse(content="ok")])
    result = agent.answer("x", session_id="sess-123")
    assert result.answer == "ok"
