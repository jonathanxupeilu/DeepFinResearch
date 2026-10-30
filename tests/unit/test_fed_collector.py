# tests/unit/test_fed_collector.py
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.fed import FedCollector
from app.monitor.models import Dimension


def make_df():
    return pd.DataFrame(
        {
            "时间": ["2026-11-05 03:00", "2026-11-10 09:00", "2026-11-06 08:00"],
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


def test_non_us_region_excluded():
    ak = MagicMock()
    ak.news_economic_baidu.return_value = pd.DataFrame(
        {"时间": ["2026-11-10 09:00"], "事件": ["FOMC利率决议"], "地区": ["中国"]}
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
        {"时间": ["garbage"], "事件": ["美联储利率决议"], "地区": ["美国"]}
    )
    events = FedCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].published_at is None
