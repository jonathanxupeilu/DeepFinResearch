# app/monitor/runner.py
import logging
from collections.abc import Sequence

from app.monitor.collectors.base import Collector
from app.monitor.models import CollectReport, Dimension
from app.monitor.store import EventStore

logger = logging.getLogger(__name__)


class MonitorRunner:
    """顺序聚合执行全部采集器，单源失败不阻断整体。"""

    def __init__(self, store: EventStore, collectors: Sequence[Collector]):
        self._store = store
        self._collectors = collectors

    @property
    def store(self) -> EventStore:
        """公开只读访问底层 EventStore，供 UI 侧显式管理连接生命周期。"""
        return self._store

    def run_all(self) -> list[CollectReport]:
        reports: list[CollectReport] = []
        for collector in self._collectors:
            dimension: Dimension | None = None
            try:
                dimension = collector.dimension
                events = collector.collect()
                added, _skipped = self._store.save_events(events)
                reports.append(CollectReport(dimension=dimension, ok=True, added=added))
            except Exception as e:  # 单源隔离是本模块核心职责
                logger.exception("采集器 %s 执行失败", dimension)
                if dimension is None:
                    # dimension 属性本身抛异常，无法归属到任何维度，跳过该源
                    continue
                reports.append(
                    CollectReport(
                        dimension=dimension,
                        ok=False,
                        added=0,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
        return reports
