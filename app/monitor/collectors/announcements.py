# app/monitor/collectors/announcements.py
import logging
from datetime import datetime, timedelta

import pandas as pd

from app.monitor.holdings import Holding
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
COL_DATE = "公告日期"
COL_TITLE = "公告标题"
COL_CODE = "股票代码"
COL_TYPE = "公告类型"


class AnnouncementsCollector:
    dimension = Dimension.ANNOUNCEMENT

    def __init__(self, holdings: list[Holding], ak=None):
        if ak is None:
            import akshare as ak
        self._ak = ak
        self._holdings = holdings

    def collect(self) -> list[MonitorEvent]:
        if not self._holdings:
            return []
        try:
            date = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
            df: pd.DataFrame = self._ak.stock_notice_report(symbol="全部", date=date)
        except Exception as e:  # noqa: BLE001 接口异常降级为空结果
            logger.warning("持仓公告采集失败: %s", e)
            return []
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                code = row.get(COL_CODE)
                title = row.get(COL_TITLE)
                if pd.isna(code) or pd.isna(title):
                    logger.warning("跳过坏行（代码或标题缺失）")
                    continue
                if not self._match_holdings(str(code)):
                    continue
                content = row.get(COL_TYPE, "")
                if pd.isna(content):
                    content = ""
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(title),
                        source="akshare:stock_notice_report",
                        content=str(content),
                        published_at=self._parse_date(row.get(COL_DATE)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    def _match_holdings(self, code: str) -> bool:
        # 列值可能是 "600519" 或 "600519.SH"，用归一化 startswith 匹配
        return any(
            code.startswith(h.code) or h.code.startswith(code) for h in self._holdings
        )

    @staticmethod
    def _parse_date(value) -> datetime | None:
        try:
            if pd.isna(value):
                return None
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 日期解析易错，失败置 None
            return None
