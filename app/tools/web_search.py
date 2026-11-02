# app/tools/web_search.py
"""联网搜索工具：Tavily REST API（Bearer 鉴权），异常降级为失败观察文本。"""

import logging
from typing import Any

import httpx

from app.tools.base import Evidence, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_TAVILY_URL = "https://api.tavily.com/search"

_SPEC = ToolSpec(
    name="web_search",
    description=(
        "联网搜索最新市场资讯、新闻与知识库之外的信息。"
        "需要时效性内容（近期事件、最新数据）或知识库检索不足时调用；query 用简体中文关键词。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词（简体中文，时效性问题须带明确时间词）",
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "month", "year"],
                "description": "限定结果时间范围；查近期行情/新闻时用 week 或 month",
            },
        },
        "required": ["query"],
    },
)


class WebSearchTool:
    spec = _SPEC

    def __init__(
        self, api_key: str, max_results: int = 5, timeout: float = 15.0
    ) -> None:
        if not api_key.strip():
            raise ValueError("TAVILY_API_KEY 为空，无法构造 web_search 工具")
        self._api_key = api_key.strip()
        self._max_results = max_results
        self._timeout = timeout

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(text="调用失败: 缺少必填参数 query")
        payload: dict[str, Any] = {"query": query, "max_results": self._max_results}
        time_range = arguments.get("time_range")
        if time_range in ("day", "week", "month", "year"):
            payload["time_range"] = time_range
        try:
            resp = httpx.post(
                _TAVILY_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001 工具容错：网络/HTTP 异常降级为观察文本
            logger.warning("web_search 搜索失败: %s", e)
            return ToolResult(text=f"联网搜索失败: {e}")
        results = [
            r
            for r in (data.get("results") or [])
            if isinstance(r, dict) and str(r.get("url", "")).strip()
        ]
        if not results:
            return ToolResult(text=f"联网未找到与「{query}」相关的结果。")
        evidence = [
            Evidence(
                source=str(r["url"]).strip(),
                text=f"{r.get('title', '')}: {r.get('content', '')}".strip(": "),
            )
            for r in results
        ]
        text = "\n\n".join(
            f"{r.get('title', '')}\n{r.get('content', '')}\nURL: {r['url']}"
            for r in results
        )
        return ToolResult(text=text, evidence=evidence)
