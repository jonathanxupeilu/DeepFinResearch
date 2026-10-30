"""依赖组装入口：UI 与 CLI 均从此取件，保证单一配置来源。"""

import logging

from app.config import get_settings
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
from app.pipeline.rag import RAGPipeline
from app.retrieval.retriever import Retriever
from app.retrieval.store import VectorStore

logger = logging.getLogger(__name__)


def build_pipeline() -> RAGPipeline:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    retriever = Retriever(store, embedder, s.top_k, s.score_threshold)
    llm = DeepSeekClient(s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model)
    return RAGPipeline(retriever, llm)


def build_ingest_components() -> Indexer:
    s = get_settings()
    store = VectorStore(persist_dir=s.chroma_dir)
    embedder = DashScopeEmbedder(
        s.dashscope_api_key, s.dashscope_base_url, s.embedding_model
    )
    return Indexer(store, embedder, s.chunk_size, s.chunk_overlap)


def build_monitor_runner() -> MonitorRunner:
    s = get_settings()
    store = EventStore(s.monitor_db_path)
    try:
        holdings: list[Holding] = load_holdings()
    except FileNotFoundError:
        logger.warning("config/holdings.json 不存在，持仓公告维度将无数据")
        holdings = []
    collectors: list[Collector] = [
        AnnouncementsCollector(holdings),
        NewsCollector(),
        MacroCollector(),
        FedCollector(),
        IndustryCollector(),
        PolicyCollector(),
    ]
    return MonitorRunner(store=store, collectors=collectors)
