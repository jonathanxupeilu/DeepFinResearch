# app/monitor/runner.py
from app.monitor.collectors.base import Collector
from app.monitor.models import CollectReport
from app.monitor.store import EventStore


class MonitorRunner:
    """顺序聚合执行全部采集器，单源失败不阻断整体。"""

    def __init__(self, store: EventStore, collectors: list[Collector]):
        self._store = store
        self._collectors = collectors

    def run_all(self) -> list[CollectReport]:
        reports: list[CollectReport] = []
        for c in self._collectors:
            dimension = c.dimension
            try:
                events = c.collect()
                added, _skipped = self._store.save_events(events)
                reports.append(CollectReport(dimension=dimension, ok=True, added=added))
            except Exception as e:  # noqa: BLE001 — 单源隔离是本模块核心职责
                reports.append(
                    CollectReport(dimension=dimension, ok=False, added=0, error=str(e))
                )
        return reports
