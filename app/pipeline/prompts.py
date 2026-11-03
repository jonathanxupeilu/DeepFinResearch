"""prompt 文案统一加载：所有提示词维护在 prompts.yaml，本文件只做加载与暴露常量。

调优任何 prompt 只改 prompts.yaml（收口原则见 AGENTS.md）。闲聊正则与
is_smalltalk 属程序逻辑，保留在本文件。
"""

import re
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_PROMPTS_PATH = Path(__file__).with_name("prompts.yaml")


def _load() -> dict:
    with _PROMPTS_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_DATA = _load()
_RAG = _DATA["rag"]
_AGENT = _DATA["agent"]
_TOOLS = _DATA["tools"]

# 单轮 RAG 通道（rag.py）
SYSTEM_PROMPT: str = _RAG["system"]
USER_TEMPLATE: str = _RAG["user_template"]
NO_CONTEXT_ANSWER: str = _RAG["no_context_answer"]
SMALLTALK_ANSWER: str = _RAG["smalltalk_answer"]

# Agent ReAct 通道（agent.py）
AGENT_SYSTEM_PROMPT: str = _AGENT["system"]

# 工具描述（LLM 决策依据，本质也是 prompt）
KNOWLEDGE_SEARCH_DESCRIPTION: str = _TOOLS["knowledge_search"]["description"]
KNOWLEDGE_SEARCH_QUERY_DESCRIPTION: str = _TOOLS["knowledge_search"]["query"]
WEB_SEARCH_DESCRIPTION: str = _TOOLS["web_search"]["description"]
WEB_SEARCH_QUERY_DESCRIPTION: str = _TOOLS["web_search"]["query"]
WEB_SEARCH_TIME_RANGE_DESCRIPTION: str = _TOOLS["web_search"]["time_range"]
CURRENT_TIME_DESCRIPTION: str = _TOOLS["current_time"]["description"]

# 闲聊分流：完整匹配打招呼/感谢/告别类输入时跳过检索（Agent 入口已废除，rag 快速通道沿用）
_SMALLTALK_RE = re.compile(
    r"^(?:你好|您好|嗨|哈喽|hello|hi|在吗|在么|早上好|上午好|中午好|下午好|晚上好|早安|晚安|"
    r"谢谢|多谢|感谢|辛苦了|麻烦了|再见|拜拜|bye+)"
    r"[!！？?。.，,~～\s]*$",
    re.IGNORECASE,
)


def is_smalltalk(text: str) -> bool:
    return bool(_SMALLTALK_RE.match(text.strip()))
