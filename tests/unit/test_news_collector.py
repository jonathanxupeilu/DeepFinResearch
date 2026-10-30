# tests/unit/test_news_collector.py
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.news import NewsCollector
from app.monitor.models import Dimension


def cls_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "标题": ["央行开展逆回购"],
            "内容": ["金额1000亿"],
            "发布时间": ["2026-10-30 09:00"],
        }
    )


def test_news_collects_titles():
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = cls_df()
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.NEWS
    assert events[0].published_at is not None


def test_news_api_failure_returns_empty():
    ak = MagicMock()
    ak.stock_info_global_cls.side_effect = RuntimeError("网络炸了")
    assert NewsCollector(ak=ak).collect() == []


def test_news_bad_time_parsed_as_none():
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {"标题": ["快讯"], "内容": ["正文"], "发布时间": ["时间未知"]}
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None


def test_news_missing_content_column_keeps_events():
    # 缺"内容"列：逐行容错只跳过坏行，不丢整批事件
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {
            "标题": ["央行开展逆回购", "国常会部署"],
            "发布时间": ["2026-10-30 09:00", "2026-10-30 10:00"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert events[0].title == "央行开展逆回购"
    assert events[0].content == ""


def test_news_bad_rows_skipped_good_rows_kept():
    # 部分坏行（NaN 标题）不丢好行；NaN 内容置空，不产出 "nan"
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {
            "标题": ["央行开展逆回购", None, "国常会部署"],
            "内容": ["金额1000亿", "内容", None],
            "发布时间": ["2026-10-30 09:00", "2026-10-30 09:01", "时间未知"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert all(e.title != "nan" for e in events)
    assert all(e.content != "nan" for e in events)
    assert events[-1].content == ""
    assert events[-1].published_at is None
