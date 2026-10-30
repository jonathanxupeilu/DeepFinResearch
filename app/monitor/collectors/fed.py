# app/monitor/collectors/fed.py
import logging

import pandas as pd

from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
COL_TIME = "时间"
COL_EVENT = "事件"
COL_REGION = "地区"

KEYWORDS = ("FOMC", "美联储", "利率决议")


class FedCollector:
    dimension = Dimension.FED

    def __init__(self, ak=None):
        if ak is None:
            import akshare as ak
        self._ak = ak

    def collect(self) -> list[MonitorEvent]:
        try:
            df: pd.DataFrame = self._ak.news_economic_baidu()
        except Exception as e:  # noqa: BLE001 接口异常降级为空结果
            logger.warning("美联储日历采集失败: %s", e)
            return []
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                event_text = row.get(COL_EVENT)
                region = row.get(COL_REGION)
                if pd.isna(event_text):
                    logger.warning("跳过坏行（事件缺失）")
                    continue
                if pd.isna(region) or "美国" not in str(region):
                    continue
                text = str(event_text)
                if not any(k in text for k in KEYWORDS):
                    continue
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=text,
                        source="akshare:news_economic_baidu",
                        published_at=self._parse_time(row.get(COL_TIME)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    @staticmethod
    def _parse_time(value) -> pd.Timestamp | None:
        try:
            if pd.isna(value):
                return None
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 时间解析易错，失败置 None
            return None
