# app/tools/knowledge_search.py
"""知识库检索工具：包装一期 Retriever，供 Agent 自主决定何时查库。"""

import logging
from typing import Any

from app.retrieval.retriever import Retriever
from app.tools.base import Evidence, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_SPEC = ToolSpec(
    name="knowledge_search",
    description=(
        "在本地投研知识库中语义检索资料。回答涉及知识库文档内容、"
        "需要事实依据或引用时优先调用；query 用简体中文关键词或问句。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索词（简体中文关键词或问句）",
            }
        },
        "required": ["query"],
    },
)


class KnowledgeSearchTool:
    spec = _SPEC

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(text="调用失败: 缺少必填参数 query")
        try:
            chunks = self._retriever.retrieve(query)
        except Exception as e:  # noqa: BLE001 工具容错：失败降级为观察文本
            logger.warning("knowledge_search 检索失败: %s", e)
            return ToolResult(text=f"知识库检索失败: {e}")
        if not chunks:
            return ToolResult(text=f"知识库中未找到与「{query}」相关的内容。")
        evidence = [Evidence(source=c.source, text=c.text) for c in chunks]
        text = "\n\n".join(f"（来源: {c.source}）\n{c.text}" for c in chunks)
        return ToolResult(text=text, evidence=evidence)
