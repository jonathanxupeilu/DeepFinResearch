import re

from app.models import Citation, RagAnswer, RetrievedChunk
from app.pipeline.prompts import (
    NO_CONTEXT_ANSWER,
    SMALLTALK_ANSWER,
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    is_smalltalk,
)
from app.retrieval.retriever import Retriever

_CITE_RE = re.compile(r"\[(\d+)\]")


def _build_citations(reply: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    """只保留回答中实际标注 [n] 的来源；n 越界忽略；一个都没标则保留全部。"""
    cited = {int(m) for m in _CITE_RE.findall(reply)}
    if not cited:
        return [
            Citation(marker=i + 1, source=c.source, text=c.text)
            for i, c in enumerate(chunks)
        ]
    return [
        Citation(marker=i + 1, source=c.source, text=c.text)
        for i, c in enumerate(chunks)
        if i + 1 in cited
    ]


class RAGPipeline:
    """一期所有 prompt 组装唯一收口。三期 ReAct / 四期 ContextBuilder / 五期角色化在此扩展。"""

    def __init__(
        self, retriever: Retriever, llm, system_prompt: str = SYSTEM_PROMPT
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.system_prompt = system_prompt  # 五期多 Agent：注入不同角色 prompt

    def build_messages(self, question: str, chunks: list[RetrievedChunk]) -> list[dict]:
        context = "\n\n".join(
            f"[{i + 1}] （来源: {c.source}）\n{c.text}" for i, c in enumerate(chunks)
        )
        return [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(context=context, question=question),
            },
        ]

    def answer(self, question: str) -> RagAnswer:
        if is_smalltalk(question):
            return RagAnswer(answer=SMALLTALK_ANSWER)
        chunks = self.retriever.retrieve(question)
        if not chunks:
            return RagAnswer(answer=NO_CONTEXT_ANSWER)
        messages = self.build_messages(question, chunks)
        reply = self.llm.chat(messages, temperature=0.3)
        return RagAnswer(answer=reply, citations=_build_citations(reply, chunks))
