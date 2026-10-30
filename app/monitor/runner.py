# app/monitor/runner.py
import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.monitor.collectors.base import Collector
from app.monitor.models import CollectReport, Dimension
from app.monitor.store import EventStore

logger = logging.getLogger(__name__)


class MonitorRunner:
    """并发聚合执行全部采集器，单源失败不阻断整体。

    - 各采集器在线程池并发跑（网络 IO 密集），入库/水位线更新在主线程串行
    - run_all 返回值始终按注入的采集器顺序排列，与完成先后无关
    - on_report 回调在每个维度落库后立即触发，供 UI 做实时进度
    """

    def __init__(self, store: EventStore, collectors: Sequence[Collector]):
        self._store = store
        self._collectors = list(collectors)

    @property
    def store(self) -> EventStore:
        """公开只读访问底层 EventStore，供 UI 侧显式管理连接生命周期。"""
        return self._store

    def _since_map(self) -> dict[Dimension, datetime | None]:
        """读每维度上次成功采集水位线；读取失败等价于从未采集。"""
        result: dict[Dimension, datetime | None] = {}
        for collector in self._collectors:
            try:
                result[collector.dimension] = self._store.get_last_collect(
                    collector.dimension
                )
            except Exception:  # noqa: BLE001
                logger.warning("读取维度 %s 水位线失败", collector.dimension)
                result[collector.dimension] = None
        return result

    def run_all(
        self, on_report: Callable[[CollectReport], None] | None = None
    ) -> list[CollectReport]:
        if not self._collectors:
            return []
        since_map = self._since_map()
        reports: dict[Dimension, CollectReport] = {}

        with ThreadPoolExecutor(max_workers=len(self._collectors)) as pool:
            future_to_collector = {
                pool.submit(
                    collector.collect, since_map.get(collector.dimension)
                ): collector
                for collector in self._collectors
            }
            for future in as_completed(future_to_collector):  # 完成即处理，快源不等待
                collector = future_to_collector[future]
                dimension: Dimension | None = None
                try:
                    dimension = collector.dimension
                    events = future.result()
                    added, _skipped = self._store.save_events(events)
                    self._store.set_last_collect(dimension, datetime.now(timezone.utc))
                    report = CollectReport(dimension=dimension, ok=True, added=added)
                except Exception as e:  # 单源隔离是本模块核心职责
                    logger.exception("采集器 %s 执行失败", dimension)
                    if dimension is None:
                        continue
                    report = CollectReport(
                        dimension=dimension,
                        ok=False,
                        added=0,
                        error=f"{type(e).__name__}: {e}",
                    )
                reports[report.dimension] = report
                if on_report is not None:
                    try:
                        on_report(report)
                    except Exception:  # noqa: BLE001 回调异常不影响采集结果
                        logger.exception("on_report 回调失败")

        # 返回值始终按注入顺序，与完成先后无关
        return [
            reports[c.dimension] for c in self._collectors if c.dimension in reports
        ]
