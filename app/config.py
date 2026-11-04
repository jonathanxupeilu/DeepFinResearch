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
    monitor_db_path: Path = Path("data/monitor.db")
    chat_history_path: Path = Path("data/chat_history.json")
    # 三期 Agent：Tavily 空 Key = 不注册 web_search，Agent 降级为纯知识库检索
    tavily_api_key: str = ""
    agent_max_iterations: int = 5
    tavily_max_results: int = 5
    # 四期观测（D019）：LangSmith 空 Key = 全静默不上报，存量链路零影响
    langsmith_api_key: str = ""
    langsmith_project: str = "deepfinresearch"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings 从环境变量注入必填字段，构造期误报
