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

MAX_CHARS = 6000   # DashScope 单条 2048 token 的字符级保护上限
BATCH_SIZE = 10    # DashScope 批量上限


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
