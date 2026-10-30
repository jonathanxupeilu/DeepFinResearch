# app/monitor/collectors/macro.py
import logging

import pandas as pd

from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)


class MacroCollector:
    dimension = Dimension.MACRO

    def __init__(self, ak=None):
        if ak is None:
            import akshare as ak
        self._ak = ak

    def collect(self) -> list[MonitorEvent]:
        indicators = [
            ("PMI", self._ak.macro_china_pmi, "制造业-同比增长"),
            ("CPI", self._ak.macro_china_cpi, "全国同比增长"),
            ("社融增量", self._ak.macro_china_shrzgm, "当月值"),
        ]
        events: list[MonitorEvent] = []
        for name, func, column in indicators:
            try:
                df: pd.DataFrame = func()
                if not isinstance(df, pd.DataFrame) or df.empty:
                    raise ValueError("返回数据非 DataFrame 或为空")
                row = df.iloc[-1]
                content = f"{name} {column}: {row[column]}（{row['月份']}）"
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=name,
                        source=f"akshare:{func.__name__ if hasattr(func, '__name__') else name}",
                        content=content,
                        published_at=None,
                    )
                )
            except Exception as e:  # noqa: BLE001 单指标失败不炸整体
                logger.warning("宏观指标 %s 采集失败: %s", name, e)
        return events
