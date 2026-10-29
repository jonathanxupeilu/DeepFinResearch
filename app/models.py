# app/models.py
import hashlib

from pydantic import BaseModel, Field, field_validator


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Document(BaseModel):
    source: str
    content: str
    doc_id: str = ""

    def model_post_init(self, __context) -> None:
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


class RagAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
