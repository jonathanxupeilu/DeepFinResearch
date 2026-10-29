import re

SYSTEM_PROMPT = """你是一名严谨的投资研究助手。规则：
1. 仅依据下方提供的【参考资料】回答问题，禁止使用资料之外的知识。
2. 引用资料时在句末标注来源编号，如 [1]、[2]。
3. 若资料不足以回答，明确说明"参考资料中未找到足够信息"，不要猜测。
4. 回答使用简体中文，条理清晰。"""

USER_TEMPLATE = """【参考资料】
{context}

【问题】
{question}"""

NO_CONTEXT_ANSWER = "知识库中未找到与该问题相关的内容，请先入库相关文档或换一种问法。"

SMALLTALK_ANSWER = "你好！我是投研助手，请直接提出你的问题，我会依据知识库资料作答。"

# 闲聊分流：完整匹配打招呼/感谢/告别类输入时跳过检索（三期 ReAct 将以 Agent 自主决策取代）
_SMALLTALK_RE = re.compile(
    r"^(?:你好|您好|嗨|哈喽|hello|hi|在吗|在么|早上好|上午好|中午好|下午好|晚上好|早安|晚安|"
    r"谢谢|多谢|感谢|辛苦了|麻烦了|再见|拜拜|bye+)"
    r"[!！？?。.，,~～\s]*$",
    re.IGNORECASE,
)


def is_smalltalk(text: str) -> bool:
    return bool(_SMALLTALK_RE.match(text.strip()))
