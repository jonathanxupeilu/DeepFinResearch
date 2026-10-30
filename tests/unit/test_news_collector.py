# tests/unit/test_news_collector.py
import pandas as pd

from app.monitor.models import Dimension
from app.monitor.collectors.news import NewsCollector


def test_news_collects_titles():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {"标题": ["央行开展逆回购"], "内容": ["金额1000亿"], "发布时间": ["2026-10-30 09:00"]}
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.NEWS
    assert events[0].published_at is not None


def test_news_api_failure_returns_empty():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.stock_info_global_cls.side_effect = RuntimeError("网络炸了")
    assert NewsCollector(ak=ak).collect() == []


def test_news_bad_time_parsed_as_none():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {"标题": ["快讯"], "内容": ["正文"], "发布时间": ["时间未知"]}
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None
