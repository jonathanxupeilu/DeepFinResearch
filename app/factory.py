"""依赖组装入口：UI 与 CLI 均从此取件，保证单一配置来源。"""

import logging

from app.config import Settings, get_settings
from app.ingest.indexer import Indexer
from app.llm.client import DeepSeekClient
from app.llm.embedding import DashScopeEmbedder
from app.monitor.collectors import (
    AnnouncementsCollector,
    FedCollector,
    IndustryCollector,
    MacroCollector,
    NewsCollector,
    PolicyCollector,
)
from app.monitor.collectors.base import Collector
from app.monitor.holdings import Holding, load_holdings
from app.monitor.runner import MonitorRunner
from app.monitor.store import EventStore
from app.pipeline.agent import AgentPipeline
from app.pipeline.rag import RAGPipeline
from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore
from app.tools.current_time import CurrentTimeTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.registry import ToolRegistry
from app.tools.web_search import WebSearchTool

logger = logging.getLogger(__name__)


def _build_llm(s: Settings) -> DeepSeekClient:
    return DeepSeekClient(
        s.deepseek_api_key,
        s.deepseek_base_url,
        s.deepseek_model,
        langsmith_api_key=s.langsmith_api_key,
        langsmith_project=s.langsmith_project,
        langsmith_endpoint=s.langsmith_endpoint,
    )


def build_pipeline() -> RAGPipeline:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = _build_llm(s)
    return RAGPipeline(retriever, llm)


def build_agent_pipeline() -> AgentPipeline:
    """三期 Agent 入口：工具注册表按配置伸缩（Tavily 无 Key 时静默降级）。"""
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = _build_llm(s)
    registry = ToolRegistry()
    registry.register(KnowledgeSearchTool(retriever))
    registry.register(CurrentTimeTool())
    if s.tavily_api_key.strip():
        registry.register(
            WebSearchTool(s.tavily_api_key, max_results=s.tavily_max_results)
        )
    return AgentPipeline(registry, llm, max_iterations=s.agent_max_iterations)


def build_ingest_components() -> Indexer:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    return Indexer(store, embedder, s.chunk_size, s.chunk_overlap)


def build_monitor_store() -> EventStore:
    """供 UI 只读路径使用：仅打开 EventStore，不构造 6 个采集器。"""
    return EventStore(get_settings().monitor_db_path)


def build_monitor_runner() -> MonitorRunner:
    s = get_settings()
    # 先加载持仓再开数据库连接，避免加载失败时泄漏已打开的连接
    try:
        holdings: list[Holding] = load_holdings()
    except FileNotFoundError:
        logger.warning("config/holdings.json 不存在，持仓公告维度将无数据")
        holdings = []
    store = EventStore(s.monitor_db_path)
    collectors: list[Collector] = [
        AnnouncementsCollector(holdings),
        # 新闻源网络不稳定（财联社曾持续挂起），单独收紧超时避免拖慢整体采集
        NewsCollector(request_timeout=20.0),
        MacroCollector(),
        FedCollector(),
        IndustryCollector(),
        PolicyCollector(),
    ]
    return MonitorRunner(store=store, collectors=collectors)
