# app/monitor/collectors/news.py
import logging
from datetime import datetime

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
# 主源：东方财富全球财经快讯（自带单条原文链接）
_EM_TITLE = "标题"
_EM_SUMMARY = "摘要"
_EM_TIME = "发布时间"
_EM_URL = "链接"
# 备源：新浪财经滚动新闻（无标题/链接列，标题取内容截断、链接用首页参考）
_SINA_TIME = "时间"
_SINA_CONTENT = "内容"
_SINA_REF_URL = "https://finance.sina.com.cn/"
_SINA_TITLE_LIMIT = 40


class NewsCollector(AkshareCollector):
    dimension = Dimension.NEWS

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        # 财联社 stock_info_global_cls 在部分网络下持续挂起且无单条链接，
        # 主源改用东财（带链接），空/失败再降级新浪
        events = self._collect_em()
        if events:
            return events
        logger.warning("东财新闻源无数据，降级新浪源")
        return self._collect_sina()

    def _collect_em(self) -> list[MonitorEvent]:
        df = self._fetch_or_none(self._ak.stock_info_global_em)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            # 逐行容错：单行缺列/NaN 只跳过该行，不丢整批事件
            try:
                title = row.get(_EM_TITLE)
                if pd.isna(title):
                    logger.warning("跳过坏行（标题缺失）")
                    continue
                summary = row.get(_EM_SUMMARY, "")
                if pd.isna(summary):
                    summary = ""
                url = row.get(_EM_URL, "")
                if pd.isna(url):
                    url = ""
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=str(title),
                        source="akshare:stock_info_global_em",
                        content=str(summary),
                        url=str(url),
                        published_at=self._parse_datetime(row.get(_EM_TIME)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events

    def _collect_sina(self) -> list[MonitorEvent]:
        df = self._fetch_or_none(self._ak.stock_info_global_sina)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        events: list[MonitorEvent] = []
        for _, row in df.iterrows():
            try:
                content = row.get(_SINA_CONTENT)
                if pd.isna(content):
                    logger.warning("跳过坏行（内容缺失）")
                    continue
                text = str(content)
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title=text[:_SINA_TITLE_LIMIT],
                        source="akshare:stock_info_global_sina",
                        content=text,
                        url=_SINA_REF_URL,
                        published_at=self._parse_datetime(row.get(_SINA_TIME)),
                    )
                )
            except Exception as e:  # noqa: BLE001 单行坏数据只跳过该行
                logger.warning("跳过坏行: %s", e)
        return events
