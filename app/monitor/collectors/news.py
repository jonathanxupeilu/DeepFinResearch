# app/monitor/collectors/news.py
import logging

import pandas as pd

from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)


class NewsCollector:
    dimension = Dimension.NEWS

    def __init__(self, ak=None):
        if ak is None:
            import akshare as ak
        self._ak = ak

    def collect(self) -> list[MonitorEvent]:
        try:
            df: pd.DataFrame = self._ak.stock_info_global_cls()
            events: list[MonitorEvent] = []
            for _, row in df.iterrows():
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(row["标题"]),
                        source="cls",
                        content=str(row["内容"]),
                        published_at=self._parse_time(row["发布时间"]),
                    )
                )
            return events
        except Exception as e:  # noqa: BLE001 接口异常降级为空结果
            logger.warning("财联社电报采集失败: %s", e)
            return []

    @staticmethod
    def _parse_time(value) -> object:
        try:
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 时间解析易错，失败置 None
            return None
