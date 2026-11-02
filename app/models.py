# app/models.py
import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Document(BaseModel):
    source: str
    content: str
    doc_id: str = ""

    def model_post_init(self, __context, /) -> None:
        if not self.doc_id:
            self.doc_id = _hash(self.content)


class Chunk(BaseModel):
    doc_id: str
    source: str
    chunk_index: int
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("chunk text 不能为空")
        return v


class RetrievedChunk(Chunk):
    score: float


class Citation(BaseModel):
    marker: int
    source: str
    text: str


class TraceStep(BaseModel):
    """Agent 决策轨迹单步：第几轮调了什么工具、参数与观察摘要。"""

    step: int
    tool: str
    arguments: dict = Field(default_factory=dict)
    observation: str = ""


class RagAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    trace: list[TraceStep] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatSession(BaseModel):
    """一轮完整对话（问答序列），历史对话面板的存储单元。"""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[ChatMessage] = Field(default_factory=list)
