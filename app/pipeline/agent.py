# app/pipeline/agent.py
"""三期 ReAct 循环：function calling 工具调用 + 全局证据编号。

与 rag.py（单轮 RAG 快速通道）并列为 pipeline 包的 prompt 组装收口。
"""

import json

from app.llm.client import ChatResponse, LLMClient, ToolCall
from app.models import RagAnswer, TraceStep
from app.pipeline.citations import build_citations
from app.pipeline.prompts import AGENT_SYSTEM_PROMPT
from app.tools.base import Evidence
from app.tools.registry import ToolRegistry

_OBSERVATION_SUMMARY_LIMIT = 200


class AgentPipeline:
    def __init__(
        self,
        registry: ToolRegistry,
        llm: LLMClient,
        max_iterations: int = 5,
        system_prompt: str = AGENT_SYSTEM_PROMPT,
    ) -> None:
        self.registry = registry
        self.llm = llm
        self.max_iterations = max_iterations  # 熔断：防工具调用死循环
        self.system_prompt = system_prompt  # 五期多 Agent：注入角色化提示词

    def answer(self, question: str) -> RagAnswer:
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        evidence: list[Evidence] = []
        trace: list[TraceStep] = []
        for step in range(1, self.max_iterations + 1):
            resp = self.llm.chat_with_tools(
                messages, self.registry.openai_tools(), temperature=0.3
            )
            if not resp.tool_calls:
                return self._final(resp.content, evidence, trace)
            messages.append(self._assistant_message(resp))
            for tc in resp.tool_calls:
                observation = self._run_tool(tc, evidence, trace, step)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": observation}
                )
        # 熔断兜底：最后一轮不给工具，强制终答
        reply = self.llm.chat(messages, temperature=0.3)
        return self._final(reply, evidence, trace)

    def _run_tool(
        self,
        tc: ToolCall,
        evidence: list[Evidence],
        trace: list[TraceStep],
        step: int,
    ) -> str:
        """执行单个工具调用：证据入全局池并编号回填观察文本，失败降级不抛出。"""
        tool = self.registry.get(tc.name)
        if tool is None:
            observation = f"未知工具: {tc.name}，请改用可用工具或直接回答。"
        else:
            result = tool.run(tc.arguments)
            if result.evidence:
                start = len(evidence) + 1
                observation = "\n\n".join(
                    f"[{start + j}]（来源: {ev.source}）\n{ev.text}"
                    for j, ev in enumerate(result.evidence)
                )
                evidence.extend(result.evidence)
            else:
                observation = result.text
        trace.append(
            TraceStep(
                step=step,
                tool=tc.name,
                arguments=tc.arguments,
                observation=observation[:_OBSERVATION_SUMMARY_LIMIT],
            )
        )
        return observation

    @staticmethod
    def _assistant_message(resp: ChatResponse) -> dict:
        return {
            "role": "assistant",
            "content": resp.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in resp.tool_calls
            ],
        }

    @staticmethod
    def _final(
        reply: str, evidence: list[Evidence], trace: list[TraceStep]
    ) -> RagAnswer:
        sources = [(e.source, e.text) for e in evidence]
        return RagAnswer(
            answer=reply, citations=build_citations(reply, sources), trace=trace
        )
