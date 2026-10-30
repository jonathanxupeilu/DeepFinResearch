# app/retrieval/stats.py
"""离线知识库存量统计：为 UI 概览卡片提供纯函数计算。"""
from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class LibraryStats(BaseModel):
    articles: int = 0  # 按 source 去重的文章数
    chunks: int = 0  # 切片总数
    categories: dict[str, int] = {}  # 分类 → 文章数
    latest_title: str | None = None  # 最新入库文章短标题
    latest_time: datetime | None = None


def _category_of(source: str) -> str:
    """分类规则：市场监控前缀 > 目录前缀 > 上传文档兜底。"""
    if source.startswith("monitor/"):
        return "市场监控"
    if "/" in source:
        return source.split("/", 1)[0]
    return "上传文档"


def _short_title(source: str, limit: int = 24) -> str:
    return Path(source).stem[:limit]


def build_library_stats(metadatas: list[dict]) -> LibraryStats:
    """从切片元数据列表聚合统计；缺 indexed_at 的存量数据只计入数量。"""
    sources = {str(m["source"]) for m in metadatas if m.get("source")}
    categories = Counter(_category_of(s) for s in sources)

    latest_title: str | None = None
    latest_time: datetime | None = None
    for source in sources:
        times = [
            m["indexed_at"]
            for m in metadatas
            if m.get("source") == source and m.get("indexed_at")
        ]
        if not times:
            continue
        t = max(times)  # 同一文章取最新一次入库时间
        parsed = datetime.fromisoformat(str(t))
        if latest_time is None or parsed > latest_time:
            latest_time = parsed
            latest_title = _short_title(source)

    return LibraryStats(
        articles=len(sources),
        chunks=len(metadatas),
        categories=dict(categories),
        latest_title=latest_title,
        latest_time=latest_time,
    )
