# 本地 RAG 问答助手（一期）实施计划

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** 构建本地知识库 RAG 问答助手：md/pdf/docx 入库 → DashScope 向量化 → Chroma 检索 → DeepSeek 生成带引用回复 + Streamlit 界面。

**Architecture:** 自研轻量分层：`ingest`（加载/切片/入库）、`retrieval`（向量库封装/检索）、`llm`（DashScope embedding / DeepSeek chat 客户端）、`pipeline`（prompt 组装唯一收口，为二/四期角色化预留）、`ui`（Streamlit）。外部调用全部走接口抽象 + tenacity 重试。

**Tech Stack:** Python 3.10+, pydantic v2 + pydantic-settings, chromadb, openai SDK（DeepSeek/DashScope 兼容模式）, pypdf, python-docx, tenacity, streamlit, pytest, ruff/black/mypy。

**设计文档:** `docs/plans/2026-10-29-local-rag-qa-design.md`

**通用约定:**
- 每个任务完成即 `git commit`，格式 `feat: <描述>` / `test: <描述>`
- 测试命令统一在项目根目录执行
- 禁止在任务外顺手实现未规划功能（YAGNI）

---

### Task 1: 项目脚手架与配置加载

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `app/__init__.py`, `app/config.py`, `tests/__init__.py`, `tests/unit/__init__.py`
- Test: `tests/unit/test_config.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_config.py
import pytest


def test_settings_requires_keys(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from app.config import Settings

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-dash")
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.deepseek_model == "deepseek-chat"
    assert s.embedding_model == "text-embedding-v3"
    assert s.chunk_size == 500
    assert s.top_k == 5
```

**Step 2:** `pytest tests/unit/test_config.py -v` → FAIL (`ModuleNotFoundError: app`)

**Step 3: 最小实现**

`pyproject.toml`：

```toml
[project]
name = "deepfinresearch"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "chromadb>=0.5",
    "openai>=1.30",
    "pypdf>=4.0",
    "python-docx>=1.1",
    "tenacity>=8.3",
    "streamlit>=1.35",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.4", "black>=24.0", "mypy>=1.10"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["e2e: 需要真实 API Key 的端到端测试"]

[tool.ruff]
line-length = 100
```

`.env.example`：

```
DEEPSEEK_API_KEY=sk-xxx
DASHSCOPE_API_KEY=sk-xxx
```

`.gitignore`：

```
.env
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
data/
knowledge/
```

`app/config.py`：

```python
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    deepseek_api_key: str
    dashscope_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    deepseek_model: str = "deepseek-chat"
    embedding_model: str = "text-embedding-v3"
    embedding_dim: int = 1024
    chunk_size: int = 500
    chunk_overlap: int = 100
    top_k: int = 5
    score_threshold: float = 0.3
    chroma_dir: Path = Path("data/chroma")
    knowledge_dir: Path = Path("knowledge")


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

另建空文件：`app/__init__.py`, `tests/__init__.py`, `tests/unit/__init__.py`。

**Step 4:** `pytest tests/unit/test_config.py -v` → PASS

**Step 5:** `git add -A && git commit -m "feat: 项目脚手架与 Pydantic Settings 配置"`

---

### Task 2: 核心数据模型

**Files:**
- Create: `app/models.py`
- Test: `tests/unit/test_models.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_models.py
import pytest
from pydantic import ValidationError

from app.models import Chunk, Citation, Document, RagAnswer, RetrievedChunk


def test_chunk_creation():
    c = Chunk(doc_id="d1", source="a.md", chunk_index=0, text="内容")
    assert c.text == "内容"


def test_chunk_rejects_empty_text():
    with pytest.raises(ValidationError):
        Chunk(doc_id="d1", source="a.md", chunk_index=0, text="  ")


def test_retrieved_chunk_has_score():
    c = RetrievedChunk(doc_id="d1", source="a.md", chunk_index=0, text="x", score=0.87)
    assert c.score == 0.87


def test_citation_fields():
    c = Citation(marker=1, source="a.md", text="片段")
    assert c.marker == 1


def test_document_auto_doc_id():
    d = Document(source="a.md", content="全文内容")
    assert len(d.doc_id) == 16
    d2 = Document(source="a.md", content="全文内容")
    assert d.doc_id == d2.doc_id  # 相同内容 → 相同 hash


def test_rag_answer_default_citations():
    a = RagAnswer(answer="回复")
    assert a.citations == []
```

**Step 2:** FAIL

**Step 3: 实现**

```python
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
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: 核心数据模型 Document/Chunk/Citation/RagAnswer"`

---

### Task 3: 文本切片器

**Files:**
- Create: `app/ingest/__init__.py`, `app/ingest/splitter.py`
- Test: `tests/unit/test_splitter.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_splitter.py
import pytest

from app.ingest.splitter import TextSplitter


def test_short_text_single_chunk():
    s = TextSplitter(chunk_size=500, chunk_overlap=100)
    assert s.split("短文本") == ["短文本"]


def test_long_text_hard_cut_with_overlap():
    s = TextSplitter(chunk_size=100, chunk_overlap=20)
    chunks = s.split("字" * 250)
    assert len(chunks) == 3
    assert chunks[0][-20:] == chunks[1][:20]  # 相邻切片有重叠


def test_paragraph_merge_not_exceed_size():
    s = TextSplitter(chunk_size=50, chunk_overlap=0)
    text = "\n".join("段" * 10 for _ in range(6))
    for c in s.split(text):
        assert len(c) <= 50


def test_empty_and_whitespace():
    s = TextSplitter(chunk_size=100, chunk_overlap=10)
    assert s.split("") == []
    assert s.split("  \n\n  ") == []


def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=50, chunk_overlap=50)
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/ingest/splitter.py


class TextSplitter:
    """按段落聚合切片；超长段落硬切并保留 overlap。"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        chunks: list[str] = []
        buf = ""
        for para in paragraphs:
            if len(para) > self.chunk_size:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(self._hard_cut(para))
                continue
            if buf and len(buf) + len(para) + 1 > self.chunk_size:
                chunks.append(buf)
                buf = para
            else:
                buf = f"{buf}\n{para}" if buf else para
        if buf:
            chunks.append(buf)
        return chunks

    def _hard_cut(self, para: str) -> list[str]:
        step = self.chunk_size - self.chunk_overlap
        return [para[i : i + self.chunk_size] for i in range(0, len(para), step)]
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: TextSplitter 段落聚合切片器"`

---

### Task 4: 文档加载器（md/txt/pdf/docx）

**Files:**
- Create: `app/ingest/loaders.py`
- Test: `tests/unit/test_loaders.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_loaders.py
from pathlib import Path

import pytest

from app.ingest.loaders import load_file, SUPPORTED


def test_supported_formats():
    assert SUPPORTED == {".md", ".txt", ".pdf", ".docx"}


def test_load_md(tmp_path: Path):
    f = tmp_path / "a.md"
    f.write_text("# 标题\n正文", encoding="utf-8")
    assert "正文" in load_file(f)


def test_load_txt(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert load_file(f) == "hello"


def test_unsupported_extension(tmp_path: Path):
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        load_file(f)


def test_load_docx(tmp_path: Path):
    from docx import Document as Docx

    f = tmp_path / "a.docx"
    d = Docx()
    d.add_paragraph("docx 正文内容")
    d.save(f)
    assert "docx 正文内容" in load_file(f)
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/ingest/loaders.py
from pathlib import Path

SUPPORTED = {".md", ".txt", ".pdf", ".docx"}


def load_file(path: Path) -> str:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"不支持的格式: {ext}（支持 {sorted(SUPPORTED)}）")
    if ext in (".md", ".txt"):
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    from docx import Document as Docx  # .docx

    return "\n".join(p.text for p in Docx(str(path)).paragraphs if p.text.strip())
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: md/txt/pdf/docx 文档加载器"`

---

### Task 5: 向量库封装（Chroma）

**Files:**
- Create: `app/retrieval/__init__.py`, `app/retrieval/store.py`
- Test: `tests/integration/test_store.py`（新建 `tests/integration/__init__.py`）

**Step 1: 写失败测试（真实 Chroma，tmp_path 隔离）**

```python
# tests/integration/test_store.py
from pathlib import Path

from app.retrieval.store import VectorStore

META = [{"doc_id": "d1", "source": "a.md", "chunk_index": 0},
        {"doc_id": "d1", "source": "a.md", "chunk_index": 1}]


def make_store(tmp_path: Path) -> VectorStore:
    return VectorStore(persist_dir=tmp_path / "chroma", collection="test")


def test_upsert_and_count(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1", "c2"], embeddings=[[0.1, 0.2], [0.3, 0.4]],
                 documents=["片段一", "片段二"], metadatas=META)
    assert store.count() == 2


def test_query_top_k(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1", "c2"], embeddings=[[1.0, 0.0], [0.0, 1.0]],
                 documents=["相关", "无关"],
                 metadatas=[META[0], {"doc_id": "d2", "source": "b.md", "chunk_index": 0}])
    hits = store.query(embedding=[0.9, 0.1], top_k=1)
    assert len(hits) == 1
    id_, doc, meta, dist = hits[0]
    assert doc == "相关"
    assert meta["source"] == "a.md"


def test_delete_document(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1"], embeddings=[[1.0, 0.0]], documents=["x"], metadatas=[META[0]])
    store.delete_document(doc_id="d1")
    assert store.count() == 0


def test_list_and_get_by_source(tmp_path: Path):
    store = make_store(tmp_path)
    store.upsert(ids=["c1"], embeddings=[[1.0]], documents=["x"], metadatas=[META[0]])
    assert "a.md" in store.list_documents()
    assert store.get_by_source("a.md") == "d1"
    assert store.get_by_source("不存在.md") is None
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/retrieval/store.py
from pathlib import Path

import chromadb


class VectorStore:
    def __init__(self, persist_dir: Path, collection: str = "knowledge") -> None:
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(collection)

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self.collection.upsert(ids=ids, embeddings=embeddings,
                               documents=documents, metadatas=metadatas)

    def query(self, embedding: list[float], top_k: int = 5):
        res = self.collection.query(query_embeddings=[embedding], n_results=top_k)
        return list(zip(res["ids"][0], res["documents"][0],
                        res["metadatas"][0], res["distances"][0]))

    def delete_document(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})

    def delete_document_by_source(self, source: str) -> None:
        self.collection.delete(where={"source": source})

    def count(self) -> int:
        return self.collection.count()

    def list_documents(self) -> list[str]:
        got = self.collection.get()
        return sorted({m["source"] for m in got["metadatas"]})

    def get_by_source(self, source: str) -> str | None:
        got = self.collection.get(where={"source": source}, include=["metadatas"])
        if not got["metadatas"]:
            return None
        return got["metadatas"][0]["doc_id"]
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: Chroma VectorStore 封装（增删查/按文档管理）"`

---

### Task 6: Embedding 客户端（DashScope）

**Files:**
- Create: `app/llm/__init__.py`, `app/llm/embedding.py`
- Test: `tests/unit/test_embedding.py`

**Step 1: 写失败测试（mock OpenAI client，不联网）**

```python
# tests/unit/test_embedding.py
from unittest.mock import MagicMock

from app.llm.embedding import BATCH_SIZE, MAX_CHARS, DashScopeEmbedder


def _mock_openai(vectors: list[list[float]]) -> MagicMock:
    client = MagicMock()
    resp = MagicMock()
    resp.data = [MagicMock(embedding=v) for v in vectors]
    client.embeddings.create.return_value = resp
    return client


def test_embed_returns_vectors():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="text-embedding-v3")
    e._client = _mock_openai([[0.1, 0.2], [0.3, 0.4]])
    assert e.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_batches_over_10():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    e._client = _mock_openai([[0.0]] * BATCH_SIZE)
    out = e.embed([str(i) for i in range(25)])  # 25 条 → 3 个批次
    assert len(out) == 25
    assert e._client.embeddings.create.call_count == 3


def test_embed_truncates_overlong_text():
    e = DashScopeEmbedder(api_key="k", base_url="http://x", model="m")
    e._client = _mock_openai([[0.0]])
    e.embed(["字" * (MAX_CHARS + 100)])
    sent = e._client.embeddings.create.call_args.kwargs["input"][0]
    assert len(sent) == MAX_CHARS
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/llm/embedding.py
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

MAX_CHARS = 6000   # DashScope 单条 2048 token 的字符级保护上限
BATCH_SIZE = 10    # DashScope 批量上限


class DashScopeEmbedder:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        cleaned = [t[:MAX_CHARS] for t in texts]
        out: list[list[float]] = []
        for i in range(0, len(cleaned), BATCH_SIZE):
            out.extend(self._embed_batch(cleaned[i : i + BATCH_SIZE]))
        return out
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: DashScope embedding 客户端（分批/重试/截断保护）"`

---

### Task 7: LLM 客户端（DeepSeek）

**Files:**
- Create: `app/llm/client.py`
- Test: `tests/unit/test_llm_client.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_llm_client.py
from unittest.mock import MagicMock

from app.llm.client import DeepSeekClient, LLMClient


def test_deepseek_satisfies_protocol():
    assert isinstance(DeepSeekClient(api_key="k", base_url="http://x", model="m"), LLMClient)


def test_chat_returns_text():
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="模型回复"))]
    c._client = MagicMock()
    c._client.chat.completions.create.return_value = resp
    assert c.chat([{"role": "user", "content": "hi"}]) == "模型回复"


def test_chat_passes_temperature():
    c = DeepSeekClient(api_key="k", base_url="http://x", model="m")
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content="x"))]
    c._client = MagicMock()
    c._client.chat.completions.create.return_value = resp
    c.chat([{"role": "user", "content": "hi"}], temperature=0.2)
    assert c._client.chat.completions.create.call_args.kwargs["temperature"] == 0.2
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/llm/client.py
from typing import Protocol

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

Message = dict[str, str]


class LLMClient(Protocol):
    """LLM 对话接口抽象：二期 ReAct / 四期多 Agent 沿此扩展。"""

    def chat(self, messages: list[Message], temperature: float = 0.7) -> str: ...


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def chat(self, messages: list[Message], temperature: float = 0.7) -> str:
        resp = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content or ""
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: DeepSeek LLM 客户端（Protocol 抽象+重试）"`

---

### Task 8: 检索器

**Files:**
- Create: `app/retrieval/retriever.py`
- Test: `tests/integration/test_retriever.py`

**Step 1: 写失败测试（真实 Chroma + mock embedder）**

```python
# tests/integration/test_retriever.py
from pathlib import Path
from unittest.mock import MagicMock

from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore


def make_retriever(tmp_path: Path):
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="t")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0, 0.0]]  # 查询向量固定
    store.upsert(ids=["c1", "c2"],
                 embeddings=[[1.0, 0.0], [0.0, 1.0]],
                 documents=["相关内容", "无关内容"],
                 metadatas=[{"doc_id": "d1", "source": "a.md", "chunk_index": 0},
                            {"doc_id": "d2", "source": "b.md", "chunk_index": 0}])
    return Retriever(store=store, embedder=embedder, top_k=2, score_threshold=0.5)


def test_retrieve_returns_sorted_chunks(tmp_path: Path):
    r = make_retriever(tmp_path)
    hits = r.retrieve("相关问题")
    assert hits[0].text == "相关内容"  # 余弦距离 0 < 1
    assert all(h.score >= 0.5 for h in hits)


def test_retrieve_filters_below_threshold(tmp_path: Path):
    r = make_retriever(tmp_path)
    hits = r.retrieve("相关问题")
    assert len(hits) == 1  # "无关内容" 距离 1.0 → score 0.0 被过滤


def test_retrieve_empty_store(tmp_path: Path):
    store = VectorStore(persist_dir=tmp_path / "chroma2", collection="t")
    embedder = MagicMock()
    embedder.embed.return_value = [[1.0]]
    r = Retriever(store=store, embedder=embedder, top_k=2, score_threshold=0.5)
    assert r.retrieve("任意") == []
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/retrieval/retriever.py
from app.models import RetrievedChunk
from app.retrieval.store import VectorStore


class Retriever:
    def __init__(self, store: VectorStore, embedder, top_k: int, score_threshold: float) -> None:
        self.store = store
        self.embedder = embedder
        self.top_k = top_k
        self.score_threshold = score_threshold

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        if self.store.count() == 0:
            return []
        qvec = self.embedder.embed([question])[0]
        hits = self.store.query(embedding=qvec, top_k=self.top_k)
        out: list[RetrievedChunk] = []
        for _id, doc, meta, dist in hits:
            score = 1.0 - dist  # chroma 默认余弦距离 → 相似度
            if score < self.score_threshold:
                continue
            out.append(RetrievedChunk(
                doc_id=meta["doc_id"], source=meta["source"],
                chunk_index=meta["chunk_index"], text=doc, score=round(score, 4),
            ))
        return out
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: Retriever top-k 检索+相似度阈值过滤"`

---

### Task 9: 入库索引器（hash 去重 + 版本替换）

**Files:**
- Create: `app/ingest/indexer.py`
- Test: `tests/integration/test_indexer.py`

**Step 1: 写失败测试**

```python
# tests/integration/test_indexer.py
from pathlib import Path
from unittest.mock import MagicMock

from app.ingest.indexer import Indexer
from app.models import Document
from app.retrieval.store import VectorStore


def make_indexer(tmp_path: Path) -> Indexer:
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="t")
    embedder = MagicMock()
    embedder.embed.side_effect = lambda texts: [[0.1] * 4 for _ in texts]
    return Indexer(store=store, embedder=embedder, chunk_size=50, chunk_overlap=10)


def test_index_adds_chunks(tmp_path: Path):
    idx = make_indexer(tmp_path)
    doc = Document(source="a.md", content="内容文字。" * 30)
    result = idx.index_document(doc)
    assert result.added > 0
    assert not result.skipped
    assert idx.store.count() == result.added


def test_index_same_content_skipped(tmp_path: Path):
    idx = make_indexer(tmp_path)
    idx.index_document(Document(source="a.md", content="相同内容"))
    r2 = idx.index_document(Document(source="a.md", content="相同内容"))
    assert r2.added == 0 and r2.skipped


def test_reindex_replaces_old_version(tmp_path: Path):
    idx = make_indexer(tmp_path)
    idx.index_document(Document(source="a.md", content="旧版本内容"))
    idx.index_document(Document(source="a.md", content="全新版本内容，完全不一样"))
    assert idx.store.list_documents() == ["a.md"]
    assert idx.store.get_by_source("a.md") != ""


def test_index_empty_document_skipped(tmp_path: Path):
    idx = make_indexer(tmp_path)
    r = idx.index_document(Document(source="empty.md", content="   \n  "))
    assert r.skipped and idx.store.count() == 0
```

**Step 2:** FAIL

**Step 3: 实现**

```python
# app/ingest/indexer.py
import logging

from pydantic import BaseModel

from app.ingest.splitter import TextSplitter
from app.models import Document
from app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


class IndexResult(BaseModel):
    source: str
    added: int = 0
    skipped: bool = False


class Indexer:
    def __init__(self, store: VectorStore, embedder,
                 chunk_size: int, chunk_overlap: int) -> None:
        self.store = store
        self.embedder = embedder
        self.splitter = TextSplitter(chunk_size, chunk_overlap)

    def index_document(self, doc: Document) -> IndexResult:
        existing_doc_id = self.store.get_by_source(doc.source)
        if existing_doc_id == doc.doc_id:  # 内容 hash 相同 → 跳过
            return IndexResult(source=doc.source, skipped=True)
        if existing_doc_id is not None:  # 文档更新 → 删旧切片
            self.store.delete_document_by_source(doc.source)

        texts = self.splitter.split(doc.content)
        if not texts:
            return IndexResult(source=doc.source, skipped=True)
        vectors = self.embedder.embed(texts)
        ids = [f"{doc.doc_id}-{i}" for i in range(len(texts))]
        metas = [{"doc_id": doc.doc_id, "source": doc.source, "chunk_index": i}
                 for i in range(len(texts))]
        self.store.upsert(ids=ids, embeddings=vectors, documents=texts, metadatas=metas)
        logger.info("入库 %s: %d 个切片", doc.source, len(texts))
        return IndexResult(source=doc.source, added=len(texts))
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: Indexer 入库（hash去重+版本替换+空文档跳过）"`

---

### Task 10: RAG Pipeline（prompt 组装唯一收口）

**Files:**
- Create: `app/pipeline/__init__.py`, `app/pipeline/rag.py`, `app/pipeline/prompts.py`
- Test: `tests/unit/test_rag_pipeline.py`

**Step 1: 写失败测试（mock retriever + mock LLM）**

```python
# tests/unit/test_rag_pipeline.py
from unittest.mock import MagicMock

from app.models import RetrievedChunk
from app.pipeline.rag import RAGPipeline

CHUNKS = [
    RetrievedChunk(doc_id="d1", source="a.md", chunk_index=0, text="巴菲特推崇护城河理论", score=0.9),
    RetrievedChunk(doc_id="d2", source="b.md", chunk_index=3, text="施洛斯偏好低 PB 筛选", score=0.8),
]


def make_pipeline(llm_reply="根据[1]……"):
    retriever = MagicMock()
    retriever.retrieve.return_value = CHUNKS
    llm = MagicMock()
    llm.chat.return_value = llm_reply
    return RAGPipeline(retriever=retriever, llm=llm), retriever, llm


def test_build_messages_contains_context_and_markers():
    pipeline, _, _ = make_pipeline()
    messages = pipeline.build_messages("什么是护城河？", CHUNKS)
    assert messages[0]["role"] == "system"
    assert "仅依据" in messages[0]["content"]  # 强约束：仅依据上下文回答
    user = messages[1]["content"]
    assert "[1]" in user and "巴菲特推崇护城河理论" in user
    assert "[2]" in user and "什么是护城河？" in user


def test_answer_returns_citations():
    pipeline, retriever, llm = make_pipeline()
    result = pipeline.answer("什么是护城河？")
    assert result.answer == "根据[1]……"
    assert len(result.citations) == 2
    assert result.citations[0].marker == 1
    assert result.citations[0].source == "a.md"
    llm.chat.assert_called_once()


def test_answer_no_retrieval_honest_refusal():
    pipeline, retriever, _ = make_pipeline()
    retriever.retrieve.return_value = []
    result = pipeline.answer("知识库里没有的问题")
    assert "未找到" in result.answer
    assert result.citations == []
    # 不得调用 LLM 硬答
```

**Step 2:** FAIL

**Step 3: 实现**

`app/pipeline/prompts.py`：

```python
SYSTEM_PROMPT = """你是一名严谨的投资研究助手。规则：
1. 仅依据下方提供的【参考资料】回答问题，禁止使用资料之外的知识。
2. 引用资料时在句末标注来源编号，如 [1]、[2]。
3. 若资料不足以回答，明确说明"参考资料中未找到足够信息"，不要猜测。
4. 回答使用简体中文，条理清晰。"""

USER_TEMPLATE = """【参考资料】
{context}

【问题】
{question}"""
```

`app/pipeline/rag.py`：

```python
from app.models import Citation, RagAnswer, RetrievedChunk
from app.pipeline.prompts import SYSTEM_PROMPT, USER_TEMPLATE
from app.retrieval.retriever import Retriever


class RAGPipeline:
    """一期所有 prompt 组装唯一收口。二期 ReAct / 三期 ContextBuilder / 四期角色化在此扩展。"""

    def __init__(self, retriever: Retriever, llm, system_prompt: str = SYSTEM_PROMPT) -> None:
        self.retriever = retriever
        self.llm = llm
        self.system_prompt = system_prompt  # 四期多 Agent：注入不同角色 prompt

    def build_messages(self, question: str, chunks: list[RetrievedChunk]) -> list[dict]:
        context = "\n\n".join(
            f"[{i + 1}] （来源: {c.source}）\n{c.text}" for i, c in enumerate(chunks)
        )
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": USER_TEMPLATE.format(context=context, question=question)},
        ]

    def answer(self, question: str) -> RagAnswer:
        chunks = self.retriever.retrieve(question)
        if not chunks:
            return RagAnswer(answer="知识库中未找到与该问题相关的内容，请先入库相关文档或换一种问法。")
        messages = self.build_messages(question, chunks)
        reply = self.llm.chat(messages, temperature=0.3)
        citations = [Citation(marker=i + 1, source=c.source, text=c.text)
                     for i, c in enumerate(chunks)]
        return RagAnswer(answer=reply, citations=citations)
```

**Step 4:** PASS → **Step 5:** `git commit -m "feat: RAG pipeline（引用标注+无检索诚实拒答+角色prompt可注入）"`

---

### Task 11: Streamlit 界面

**Files:**
- Create: `app/ui/__init__.py`, `app/ui/app.py`, `app/factory.py`
- Test: `tests/unit/test_factory.py`（工厂组装逻辑可测；UI 本体手动冒烟）

**Step 1: 写失败测试（工厂依赖组装）**

```python
# tests/unit/test_factory.py
from unittest.mock import patch

import pytest

from app.factory import build_pipeline, build_ingest_components


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k1")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "k2")


def test_build_pipeline_types(env):
    pipeline = build_pipeline()
    from app.pipeline.rag import RAGPipeline
    assert isinstance(pipeline, RAGPipeline)


def test_build_ingest_components(env):
    indexer = build_ingest_components()
    from app.ingest.indexer import Indexer
    assert isinstance(indexer, Indexer)
```

**Step 2:** FAIL

**Step 3: 实现**

`app/factory.py`：

```python
"""依赖组装入口：UI 与 CLI 均从此取件，保证单一配置来源。"""
from pathlib import Path

from app.config import get_settings
from app.ingest.indexer import Indexer
from app.llm.client import DeepSeekClient
from app.llm.embedding import DashScopeEmbedder
from app.pipeline.rag import RAGPipeline
from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore


def build_pipeline() -> RAGPipeline:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(s.dashscope_api_key, s.dashscope_base_url, s.embedding_model)
    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    return RAGPipeline(retriever, llm)


def build_ingest_components() -> Indexer:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(s.dashscope_api_key, s.dashscope_base_url, s.embedding_model)
    return Indexer(store, embedder, s.chunk_size, s.chunk_overlap)
```

`app/ui/app.py`（Streamlit，聊天 + 侧边栏知识库管理）：

```python
import streamlit as st

from app.factory import build_ingest_components, build_pipeline
from app.ingest.loaders import load_file

st.set_page_config(page_title="DeepFinResearch", page_icon="⚙️")
st.title("⚙️ DeepFinResearch · 本地知识库问答")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("📚 知识库管理")
    uploaded = st.file_uploader("上传文档", type=["md", "txt", "pdf", "docx"])
    if uploaded and st.button("入库"):
        tmp = Path("data/uploads") / uploaded.name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(uploaded.getvalue())
        try:
            text = load_file(tmp)
            doc = Document(source=uploaded.name, content=text)
            result = build_ingest_components().index_document(doc)
            if result.skipped:
                st.info(f"「{uploaded.name}」内容未变化，已跳过")
            else:
                st.success(f"「{uploaded.name}」入库成功：{result.added} 个切片")
        except ValueError as e:
            st.error(str(e))

    if st.button("刷新文档列表"):
        st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("输入你的问题…"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("检索知识库并生成回答…"):
            result = build_pipeline().answer(question)
        st.markdown(result.answer)
        if result.citations:
            with st.expander("📎 引用来源"):
                for c in result.citations:
                    st.markdown(f"**[{c.marker}] {c.source}**\n\n> {c.text[:200]}…")
    st.session_state.messages.append({"role": "assistant", "content": result.answer})
```

（注意：`app.py` 顶部需补 `from pathlib import Path` 与 `from app.models import Document`。）

**Step 4:** `pytest tests/unit/test_factory.py -v` → PASS；手动冒烟 `streamlit run app/ui/app.py` 确认页面可开

**Step 5:** `git commit -m "feat: Streamlit 聊天界面+知识库管理+依赖工厂"`

---

### Task 12: E2E 冒烟测试 + README 收尾

**Files:**
- Create: `tests/e2e/test_smoke.py`, `README.md`
- Test: `tests/e2e/test_smoke.py`

**Step 1: 写测试（真实 API，默认跳过）**

```python
# tests/e2e/test_smoke.py
import os

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("DEEPSEEK_API_KEY") or not os.getenv("DASHSCOPE_API_KEY"),
        reason="需要真实 API Key，设置后运行: pytest tests/e2e -m e2e",
    ),
]


def test_full_rag_roundtrip(tmp_path, monkeypatch):
    """入库 → 检索 → 问答 全链路冒烟（真实 Chroma + 真实 API）。"""
    from app.ingest.indexer import Indexer
    from app.models import Document
    from app.retrieval.store import VectorStore
    from app.config import get_settings

    monkeypatch.setattr("app.config.get_settings", None)  # 防缓存串扰（如需要）
    s = get_settings()
    store = VectorStore(persist_dir=tmp_path / "chroma", collection="smoke")
    from app.llm.embedding import DashScopeEmbedder
    from app.llm.client import DeepSeekClient
    embedder = DashScopeEmbedder(s.dashscope_api_key, s.dashscope_base_url, s.embedding_model)
    idx = Indexer(store, embedder, s.chunk_size, s.chunk_overlap)
    result = idx.index_document(Document(source="测试.md", content="巴菲特的护城河理论指企业拥有的可持续竞争优势。"))
    assert result.added > 0

    from app.retrieval.retriever import Retriever
    from app.pipeline.rag import RAGPipeline
    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    answer = RAGPipeline(retriever, llm).answer("什么是护城河理论？")
    assert answer.answer
    assert len(answer.citations) >= 1
```

**Step 2:** 无 Key 时 SKIP 为预期；配置 `.env` 后 `pytest tests/e2e -m e2e -v` → PASS

**Step 3: README.md**

```markdown
# DeepFinResearch

本地 RAG 智能问答助手（一期）。路线图：RAG 问答 → 工具调用/ReAct → 记忆 → 多Agent → PTC 财务计算。

## 快速开始
1. `python -m venv .venv && .venv/Scripts/activate`（Windows）
2. `pip install -e ".[dev]"`
3. `cp .env.example .env` 并填入 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`
4. `streamlit run app/ui/app.py`

## 测试
- `pytest tests/unit tests/integration -v`（无需真实 Key）
- `pytest tests/e2e -m e2e -v`（需真实 Key）
```

**Step 4:** 全量质量门禁：`ruff check . --fix && black . && mypy app && pytest tests/unit tests/integration -v` 全绿

**Step 5:** `git add -A && git commit -m "feat: e2e 冒烟测试与 README"`

---

### Task 13: CLI 问答入口

**Files:**
- Create: `app/cli.py`
- Modify: `README.md`（快速开始追加 CLI 用法）
- Test: `tests/unit/test_cli.py`

**Step 1: 写失败测试（注入 input/print，不真实调用）**

```python
# tests/unit/test_cli.py
from unittest.mock import MagicMock

from app.cli import format_answer, run
from app.models import Citation, RagAnswer


def _mock_pipeline(answer: str, citations: list[Citation] | None = None) -> MagicMock:
    p = MagicMock()
    p.answer.return_value = RagAnswer(answer=answer, citations=citations or [])
    return p


def test_format_answer_with_citations():
    result = RagAnswer(answer="结论 [1]",
                       citations=[Citation(marker=1, source="a.md", text="片段")])
    text = format_answer(result)
    assert "结论 [1]" in text
    assert "[1] a.md" in text


def test_format_answer_no_citations():
    assert format_answer(RagAnswer(answer="纯回复")) == "纯回复"


def test_run_repl_loop():
    pipeline = _mock_pipeline("回答内容")
    inputs = iter(["什么是护城河？", "/exit"])
    out: list[str] = []
    run(pipeline, input_fn=lambda _: next(inputs), output=out.append)
    pipeline.answer.assert_called_once_with("什么是护城河？")
    assert any("回答内容" in line for line in out)


def test_run_ignores_blank_and_eof():
    pipeline = _mock_pipeline("x")
    inputs = iter(["", "  "])  # 空输入后 EOF
    out: list[str] = []
    run(pipeline, input_fn=lambda _: next(inputs), output=out.append)  # EOFError 正常退出
    pipeline.answer.assert_not_called()


def test_run_exit_aliases():
    pipeline = _mock_pipeline("x")
    for alias in ("/exit", "/quit", "exit", "q"):
        inputs = iter([alias])
        out: list[str] = []
        run(pipeline, input_fn=lambda _: next(inputs), output=out.append)
    pipeline.answer.assert_not_called()
```

**Step 2:** `pytest tests/unit/test_cli.py -v` → FAIL (`ModuleNotFoundError`)

**Step 3: 实现**

```python
# app/cli.py
"""终端问答入口：python -m app.cli"""
import sys

from app.factory import build_pipeline
from app.models import RagAnswer

EXIT_WORDS = {"/exit", "/quit", "exit", "quit", "q"}


def format_answer(result: RagAnswer) -> str:
    lines = [result.answer]
    if result.citations:
        lines.append("")
        lines.append("📎 引用来源:")
        lines.extend(f"  [{c.marker}] {c.source}" for c in result.citations)
    return "\n".join(lines)


def run(pipeline, input_fn=input, output=print) -> None:
    output("⚙️ DeepFinResearch 投研顾问（输入 /exit 退出）")
    while True:
        try:
            question = input_fn("❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            output("再见。")
            return
        if not question:
            continue
        if question.lower() in EXIT_WORDS:
            output("再见。")
            return
        result = pipeline.answer(question)
        output(format_answer(result))


def main() -> int:
    run(build_pipeline())
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

README 快速开始追加：

```markdown
- 终端问答：`python -m app.cli`
```

**Step 4:** PASS；质量门禁 `ruff check . && black . && mypy app` 全绿

**Step 5:** `git commit -m "feat: CLI 问答入口（REPL+引用展示+优雅退出）"`

---

## 完成标准（Definition of Done）

- [ ] `pytest tests/unit tests/integration` 全绿（无 Key 依赖）
- [ ] `ruff check .` / `black --check .` / `mypy app` 通过
- [ ] `streamlit run app/ui/app.py` 手动冒烟：上传文档 → 提问 → 带引用回答
- [ ] `python -m app.cli` 手动冒烟：问答 → 引用展示 → /exit 退出
- [ ] 每个 Task 均有独立 commit

