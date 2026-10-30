# app/monitor/collectors/news.py
import logging

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
_COL_TITLE = "标题"
_COL_CONTENT = "内容"
_COL_TIME = "发布时间"


class NewsCollector(AkshareCollector):
    dimension = Dimension.NEWS

    def collect(self) -> list[MonitorEvent]:
        df = self._fetch_or_none(self._ak.stock_info_global_cls)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                title = row.get(_COL_TITLE)
                content = row.get(_COL_CONTENT, "")
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
                        published_at=self._parse_datetime(row.get(_COL_TIME)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events
