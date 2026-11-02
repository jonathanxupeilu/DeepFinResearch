# tests/unit/test_news_collector.py
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.news import NewsCollector
from app.monitor.models import Dimension


def em_df() -> pd.DataFrame:
    # 真实接口 stock_info_global_em 列结构：标题/摘要/发布时间/链接
    return pd.DataFrame(
        {
            "标题": ["日本经济财政大臣表态"],
            "摘要": ["将重点观察供需缺口"],
            "发布时间": ["2026-11-02 11:04:14"],
            "链接": ["https://finance.eastmoney.com/a/1.html"],
        }
    )


def sina_df() -> pd.DataFrame:
    # 真实接口 stock_info_global_sina 列结构：时间/内容（无标题/链接列）
    return pd.DataFrame(
        {
            "时间": ["2026-11-02 11:03:01"],
            "内容": ["隔夜SHIBOR报1.2860%，下跌0.30个基点。"],
        }
    )


def test_news_collects_from_em_with_url():
    ak = MagicMock()
    ak.stock_info_global_em.return_value = em_df()
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.NEWS
    assert events[0].source == "akshare:stock_info_global_em"
    assert events[0].url == "https://finance.eastmoney.com/a/1.html"
    assert events[0].published_at is not None


def test_news_em_failure_falls_back_to_sina():
    ak = MagicMock()
    ak.stock_info_global_em.side_effect = RuntimeError("网络炸了")
    ak.stock_info_global_sina.return_value = sina_df()
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].source == "akshare:stock_info_global_sina"
    assert events[0].url == "https://finance.sina.com.cn/"
    assert events[0].title == "隔夜SHIBOR报1.2860%，下跌0.30个基点。"


def test_news_both_sources_fail_returns_empty():
    ak = MagicMock()
    ak.stock_info_global_em.side_effect = RuntimeError("em 炸了")
    ak.stock_info_global_sina.side_effect = RuntimeError("sina 炸了")
    assert NewsCollector(ak=ak).collect() == []


def test_news_em_bad_time_parsed_as_none():
    ak = MagicMock()
    ak.stock_info_global_em.return_value = pd.DataFrame(
        {
            "标题": ["快讯"],
            "摘要": ["正文"],
            "发布时间": [None],
            "链接": ["https://example.com/1"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None


def test_news_em_missing_summary_keeps_events():
    # 缺"摘要"列：逐行容错只跳过坏行，不丢整批事件
    ak = MagicMock()
    ak.stock_info_global_em.return_value = pd.DataFrame(
        {
            "标题": ["央行开展逆回购", "国常会部署"],
            "发布时间": ["2026-11-02 09:00:00", "2026-11-02 10:00:00"],
            "链接": ["https://example.com/1", "https://example.com/2"],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert events[0].title == "央行开展逆回购"
    assert events[0].content == ""


def test_news_em_bad_rows_skipped_good_rows_kept():
    # 部分坏行（NaN 标题）不丢好行；NaN 摘要置空，不产出 "nan"；坏行时间解析置 None
    ak = MagicMock()
    ak.stock_info_global_em.return_value = pd.DataFrame(
        {
            "标题": ["央行开展逆回购", None, "国常会部署"],
            "摘要": ["金额1000亿", "内容", None],
            "发布时间": [
                "2026-11-02 09:00:00",
                "2026-11-02 09:01:00",
                None,
            ],
            "链接": [
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
            ],
        }
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 2
    assert all(e.title != "nan" for e in events)
    assert all(e.content != "nan" for e in events)
    assert events[-1].content == ""
    assert events[-1].published_at is None
