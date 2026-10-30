# tests/unit/test_fed_collector.py
from datetime import date, datetime, time
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.fed import FedCollector
from app.monitor.models import Dimension


def make_df():
    # 真实接口 news_economic_baidu 列结构：日期(date 对象) + 时间(time 对象)
    return pd.DataFrame(
        {
            "日期": [date(2026, 11, 5), date(2026, 11, 10), date(2026, 11, 6)],
            "时间": [time(3, 0), time(9, 0), time(8, 0)],
            "事件": ["FOMC利率决议", "中国进出口数据发布", "美联储官员讲话"],
            "地区": ["美国", "中国", "美国"],
        }
    )


def test_collects_fed_events():
    ak = MagicMock()
    ak.news_economic_baidu.return_value = make_df()
    events = FedCollector(ak=ak).collect()
    assert len(events) == 2
    assert {e.dimension for e in events} == {Dimension.FED}
    assert events[0].source == "akshare:news_economic_baidu"
    assert events[0].published_at is not None


def test_news_economic_baidu_called_with_today_date():
    # C4：news_economic_baidu 的 date 默认硬编码 '20241107'，必须显式传当天
    ak = MagicMock()
    ak.news_economic_baidu.return_value = make_df()
    FedCollector(ak=ak).collect()
    ak.news_economic_baidu.assert_called_once_with(
        date=datetime.now().strftime("%Y%m%d")
    )


def test_non_us_region_excluded():
    ak = MagicMock()
    ak.news_economic_baidu.return_value = pd.DataFrame(
        {
            "日期": [date(2026, 11, 10)],
            "时间": [time(9, 0)],
            "事件": ["FOMC利率决议"],
            "地区": ["中国"],
        }
    )
    events = FedCollector(ak=ak).collect()
    assert events == []


def test_api_failure_returns_empty():
    ak = MagicMock()
    ak.news_economic_baidu.side_effect = RuntimeError("接口挂了")
    events = FedCollector(ak=ak).collect()
    assert events == []


def test_bad_time_parsed_to_none():
    ak = MagicMock()
    ak.news_economic_baidu.return_value = pd.DataFrame(
        {
            "日期": [date(2026, 11, 5)],
            "时间": [None],  # 坏时间置 None，组合后解析失败
            "事件": ["美联储利率决议"],
            "地区": ["美国"],
        }
    )
    events = FedCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None
