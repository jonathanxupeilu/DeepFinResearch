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
