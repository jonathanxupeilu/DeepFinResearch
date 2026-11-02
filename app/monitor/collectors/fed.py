# app/monitor/collectors/fed.py
import logging
from datetime import datetime

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
_COL_DATE = "日期"
_COL_TIME = "时间"
_COL_EVENT = "事件"
_COL_REGION = "地区"
_COL_ACTUAL = "公布"
_COL_EXPECT = "预期"
_COL_PREV = "前值"
_COL_IMPORTANCE = "重要性"

_KEYWORDS = ("FOMC", "美联储", "利率决议")
_FED_REF_URL = "https://www.federalreserve.gov/"


def _build_content(row: pd.Series, region: str) -> str:
    """组合地区与公布/预期/前值/重要性为正文，NaN 字段跳过，避免"无内容"。"""
    parts = [f"地区：{region}"]
    for label, col in (
        ("公布", _COL_ACTUAL),
        ("预期", _COL_EXPECT),
        ("前值", _COL_PREV),
        ("重要性", _COL_IMPORTANCE),
    ):
        value = row.get(col)
        if not pd.isna(value):
            parts.append(f"{label}：{value}")
    return "；".join(parts)


class FedCollector(AkshareCollector):
    dimension = Dimension.FED

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        # date 默认硬编码 '20241107'，必须显式传当天
        df = self._fetch_or_none(
            self._ak.news_economic_baidu, date=datetime.now().strftime("%Y%m%d")
        )
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                event_text = row.get(_COL_EVENT)
                region = row.get(_COL_REGION)
                if pd.isna(event_text):
                    logger.warning("跳过坏行（事件缺失）")
                    continue
                if pd.isna(region) or "美国" not in str(region):
                    continue
                text = str(event_text)
                if not any(k in text for k in _KEYWORDS):
                    continue
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=text,
                        source="akshare:news_economic_baidu",
                        content=_build_content(row, str(region)),
                        url=_FED_REF_URL,
                        published_at=self._parse_datetime(
                            f"{row.get(_COL_DATE)} {row.get(_COL_TIME)}"
                        ),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events
