# app/monitor/collectors/industry.py
import logging

import pandas as pd

from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
SGE_DATE_COL = "date"
SGE_CLOSE_COL = "Au99.99收盘"
BDI_DATE_COL = "日期"
BDI_CLOSE_COL = "收盘"


class IndustryCollector:
    dimension = Dimension.INDUSTRY

    def __init__(self, ak=None):
        if ak is None:
            import akshare as ak
        self._ak = ak

    def collect(self) -> list[MonitorEvent]:
        # (标题, 接口, 日期列, 数值列, 接口名字符串)
        indicators = [
            (
                "黄金",
                self._ak.spot_hist_sge,
                SGE_DATE_COL,
                SGE_CLOSE_COL,
                "spot_hist_sge",
            ),
            (
                "BDI运价",
                self._ak.index_bdi_hist,
                BDI_DATE_COL,
                BDI_CLOSE_COL,
                "index_bdi_hist",
            ),
        ]
        events: list[MonitorEvent] = []
        for name, func, date_col, value_col, api_name in indicators:
            try:
                df: pd.DataFrame = func()
                if not isinstance(df, pd.DataFrame) or df.empty:
                    raise ValueError("返回数据非 DataFrame 或为空")
                row = df.iloc[-1]
                content = f"{name}: {row[value_col]}（{row[date_col]}）"
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=name,
                        source=f"akshare:{api_name}",
                        content=content,
                        published_at=self._parse_date(row[date_col]),
                    )
                )
            except Exception as e:  # noqa: BLE001 单指标失败不炸整体
                logger.warning("行业指标 %s 采集失败: %s", name, e)
        return events

    @staticmethod
    def _parse_date(value) -> pd.Timestamp | None:
        try:
            if pd.isna(value):
                return None
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 日期解析易错，失败置 None
            return None
