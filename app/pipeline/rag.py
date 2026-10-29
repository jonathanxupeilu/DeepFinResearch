from app.models import Citation, RagAnswer, RetrievedChunk
from app.pipeline.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from app.retrieval.retriever import Retriever


class RAGPipeline:
    """一期所有 prompt 组装唯一收口。二期 ReAct / 三期 ContextBuilder / 四期角色化在此扩展。"""

    def __init__(
        self, retriever: Retriever, llm, system_prompt: str = SYSTEM_PROMPT
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.system_prompt = system_prompt  # 四期多 Agent：注入不同角色 prompt

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
        chunks = self.retriever.retrieve(question)
        if not chunks:
            return RagAnswer(
                answer="知识库中未找到与该问题相关的内容，请先入库相关文档或换一种问法。"
            )
        messages = self.build_messages(question, chunks)
        reply = self.llm.chat(messages, temperature=0.3)
        citations = [
            Citation(marker=i + 1, source=c.source, text=c.text)
            for i, c in enumerate(chunks)
        ]
        return RagAnswer(answer=reply, citations=citations)
