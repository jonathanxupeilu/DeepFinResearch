"""依赖组装入口：UI 与 CLI 均从此取件，保证单一配置来源。"""

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
