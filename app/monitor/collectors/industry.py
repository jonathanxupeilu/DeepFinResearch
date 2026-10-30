# app/monitor/collectors/industry.py
import logging

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
_SGE_DATE_COL = "date"
_SGE_CLOSE_COL = "Au99.99收盘"
_BDI_DATE_COL = "日期"
_BDI_CLOSE_COL = "最新值"


class IndustryCollector(AkshareCollector):
    dimension = Dimension.INDUSTRY

    def collect(self) -> list[MonitorEvent]:
        # (标题, 接口, 日期列, 数值列, 接口名字符串)
        indicators = [
            (
                "黄金",
                self._ak.spot_hist_sge,
                _SGE_DATE_COL,
                _SGE_CLOSE_COL,
                "spot_hist_sge",
            ),
            (
                "BDI运价",
                self._ak.macro_shipping_bdi,
                _BDI_DATE_COL,
                _BDI_CLOSE_COL,
                "macro_shipping_bdi",
            ),
        ]
        events: list[MonitorEvent] = []
        for name, func, date_col, value_col, api_name in indicators:
            try:
                df: pd.DataFrame = func()
                if not isinstance(df, pd.DataFrame) or df.empty:
                    raise ValueError("返回数据非 DataFrame 或为空")
                row = df.iloc[-1]
                # I4 防御：末行日期/数值为 NaN 时跳过，不产出脏事件
                if pd.isna(row[date_col]) or pd.isna(row[value_col]):
                    logger.warning("行业指标 %s 末行日期/数值为 NaN，跳过", name)
                    continue
                content = f"{name}: {row[value_col]}（{row[date_col]}）"
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=name,
                        source=f"akshare:{api_name}",
                        content=content,
                        published_at=self._parse_datetime(row[date_col]),
                    )
                )
            except Exception as e:  # noqa: BLE001 单指标失败不炸整体
                logger.warning("行业指标 %s 采集失败: %s", name, e)
        return events
