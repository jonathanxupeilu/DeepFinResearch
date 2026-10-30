# app/monitor/collectors/announcements.py
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.holdings import Holding
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
_COL_DATE = "公告日期"
_COL_TITLE = "公告标题"
_COL_CODE = "股票代码"
_COL_TYPE = "公告类型"

# stock_notice_report 的 date 是单日参数，采集窗口为近 N 天（含今天）
_WINDOW_DAYS = 7


def _norm_code(value: Any) -> str:
    """股票码归一化：剥交易所后缀、去空白，只留主体码。"""
    return str(value).split(".")[0].strip()


class AnnouncementsCollector(AkshareCollector):
    dimension = Dimension.ANNOUNCEMENT

    def __init__(self, holdings: list[Holding], ak=None):
        super().__init__(ak)
        self._holdings = holdings

    def collect(self) -> list[MonitorEvent]:
        if not self._holdings:
            return []
        df = self._fetch_window()
        if df is None or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                code = row.get(_COL_CODE)
                title = row.get(_COL_TITLE)
                if pd.isna(code) or pd.isna(title):
                    logger.warning(
                        "跳过坏行（代码或标题缺失）: code=%r title=%r", code, title
                    )
                    continue
                if not self._match_holdings(str(code)):
                    continue
                content = row.get(_COL_TYPE, "")
                if pd.isna(content):
                    content = ""
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(title),
                        source="akshare:stock_notice_report",
                        content=str(content),
                        published_at=self._parse_datetime(row.get(_COL_DATE)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    def _fetch_window(self) -> pd.DataFrame | None:
        """逐日采集近 7 天（含今天）的公告并合并；单日失败跳过。"""
        frames: list[pd.DataFrame] = []
        for offset in range(_WINDOW_DAYS):
            date = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                df: pd.DataFrame = self._ak.stock_notice_report(
                    symbol="全部", date=date
                )
            except Exception as e:  # noqa: BLE001 单日失败不炸整体
                logger.warning("持仓公告 %s 单日采集失败，跳过: %s", date, e)
                continue
            if isinstance(df, pd.DataFrame) and not df.empty:
                frames.append(df)
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    def _match_holdings(self, code: str) -> bool:
        # 归一化后精确相等：避免 startswith 的误配（6005191→600519）与漏配
        norm = _norm_code(code)
        return any(norm == _norm_code(h.code) for h in self._holdings)
