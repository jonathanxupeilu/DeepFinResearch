# tests/unit/test_news_collector.py
from datetime import date, time
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.news import NewsCollector
from app.monitor.models import Dimension


def cls_df() -> pd.DataFrame:
    # 真实接口 stock_info_global_cls 列结构：发布日期(date 对象) + 发布时间(time 对象)
    return pd.DataFrame(
        {
            "发布日期": [date(2026, 10, 30)],
            "发布时间": [time(9, 0)],
            "标题": ["央行开展逆回购"],
            "内容": ["金额1000亿"],
        }
    )


def test_news_collects_titles():
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = cls_df()
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.NEWS
    assert events[0].published_at is not None  # 双列组合解析成功


def test_news_api_failure_returns_empty():
    ak = MagicMock()
    ak.stock_info_global_cls.side_effect = RuntimeError("网络炸了")
    assert NewsCollector(ak=ak).collect() == []


def test_news_bad_time_parsed_as_none():
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {
            "发布日期": [date(2026, 10, 30)],
            "发布时间": [None],  # 坏时间置 None，组合后解析失败
            "标题": ["快讯"],
            "内容": ["正文"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None


def test_news_missing_content_column_keeps_events():
    # 缺"内容"列：逐行容错只跳过坏行，不丢整批事件
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {
            "发布日期": [date(2026, 10, 30), date(2026, 10, 30)],
            "发布时间": [time(9, 0), time(10, 0)],
            "标题": ["央行开展逆回购", "国常会部署"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert events[0].title == "央行开展逆回购"
    assert events[0].content == ""


def test_news_bad_rows_skipped_good_rows_kept():
    # 部分坏行（NaN 标题）不丢好行；NaN 内容置空，不产出 "nan"；坏行时间解析置 None
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {
            "发布日期": [date(2026, 10, 30), date(2026, 10, 30), date(2026, 10, 30)],
            "发布时间": [time(9, 0), time(9, 1), None],
            "标题": ["央行开展逆回购", None, "国常会部署"],
            "内容": ["金额1000亿", "内容", None],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert all(e.title != "nan" for e in events)
    assert all(e.content != "nan" for e in events)
    assert events[-1].content == ""
    assert events[-1].published_at is None
