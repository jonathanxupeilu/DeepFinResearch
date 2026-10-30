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
_COL_CODE = "代码"
_COL_TYPE = "公告类型"
_COL_URL = "网址"

# stock_notice_report 的 date 是单日参数，采集窗口为近 N 天（含今天）
_WINDOW_DAYS = 7


def _norm_code(value: Any) -> str:
    """股票码归一化：剥交易所后缀、去空白，只留主体码。"""
    return str(value).split(".")[0].strip()


class AnnouncementsCollector(AkshareCollector):
    dimension = Dimension.ANNOUNCEMENT

    def __init__(self, holdings: list[Holding], ak=None, request_timeout: float = 60.0):
        super().__init__(ak, request_timeout=request_timeout)
        self._holdings = holdings

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        if not self._holdings:
            return []
        df = self._fetch_window(since)
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
                url = row.get(_COL_URL, "")
                if pd.isna(url):
                    url = ""
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(title),
                        source="akshare:stock_notice_report",
                        content=str(content),
                        url=str(url),
                        published_at=self._parse_datetime(row.get(_COL_DATE)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    def _fetch_window(self, since: datetime | None = None) -> pd.DataFrame | None:
        """逐日采集近 N 天（含今天）的公告并合并；单日失败/超时跳过。

        since 为该维度上次成功采集水位线：窗口 = 距今天数+1，夹在 [1, 7]。
        首次采集（since 为空）保持 7 天全量窗口。
        """
        window_days = _WINDOW_DAYS
        if since is not None:
            elapsed = (datetime.now().date() - since.date()).days
            window_days = min(max(elapsed + 1, 1), _WINDOW_DAYS)
        frames: list[pd.DataFrame] = []
        for offset in range(window_days):
            date = (datetime.now() - timedelta(days=offset)).strftime("%Y%m%d")
            # 走基类超时保护：单日卡死/异常均降级为 None 跳过
            df = self._fetch_or_none(
                self._ak.stock_notice_report, symbol="全部", date=date
            )
            if isinstance(df, pd.DataFrame) and not df.empty:
                frames.append(df)
        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    def _match_holdings(self, code: str) -> bool:
        # 归一化后精确相等：避免 startswith 的误配（6005191→600519）与漏配
        norm = _norm_code(code)
        return any(norm == _norm_code(h.code) for h in self._holdings)
