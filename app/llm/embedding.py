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
