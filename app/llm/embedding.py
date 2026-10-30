# app/llm/embedding.py
import logging

from openai import APIConnectionError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# 官方限制：text-embedding-v3 单条最长 8192 token（batch 上限 10 条）。
# 中英混合按 ~1.5 字符/token 保守换算 → 8192 token ≈ 12000 字符。
# 入库切片远小于此值，此上限仅为防御性保护（见 docs.bailian text-embedding-synchronous-api）。
MAX_CHARS = 12000
BATCH_SIZE = 10  # DashScope 批量上限


class DashScopeEmbedder:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    @retry(
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        reraise=True,
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def embed(self, texts: list[str]) -> list[list[float]]:
        cleaned = []
        for t in texts:
            if len(t) > MAX_CHARS:
                logger.warning("文本超过 %d 字符已截断: %.20s…", MAX_CHARS, t)
                t = t[:MAX_CHARS]
            cleaned.append(t)
        out: list[list[float]] = []
        for i in range(0, len(cleaned), BATCH_SIZE):
            out.extend(self._embed_batch(cleaned[i : i + BATCH_SIZE]))
        return out
