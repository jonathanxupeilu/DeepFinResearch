# app/monitor/collectors/news.py
import logging
from datetime import datetime

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
        except Exception as e:  # noqa: BLE001 接口异常降级为空结果
            logger.warning("财联社电报采集失败: %s", e)
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                title = row.get("标题")
                content = row.get("内容", "")
                if pd.isna(title):
                    logger.warning("跳过坏行（标题缺失）")
                    continue
                if pd.isna(content):
                    content = ""
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(title),
                        source="cls",
                        content=str(content),
                        published_at=self._parse_time(row.get("发布时间")),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    @staticmethod
    def _parse_time(value) -> datetime | None:
        try:
            if pd.isna(value):
                return None
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 时间解析易错，失败置 None
            return None
