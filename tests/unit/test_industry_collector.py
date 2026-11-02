# tests/unit/test_industry_collector.py
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.industry import IndustryCollector
from app.monitor.models import Dimension


def fake_ak(m):
    m.spot_hist_sge.return_value = pd.DataFrame(
        {
            "date": ["2026-10-29"],
            "open": [779.0],
            "close": [780.5],
            "low": [778.2],
            "high": [781.3],
        }
    )
    m.macro_shipping_bdi.return_value = pd.DataFrame(
        {"日期": ["2026-10-29"], "最新值": [2712.0]}
    )
    return m


def test_collects_one_event_per_indicator():
    c = IndustryCollector(ak=fake_ak(MagicMock()))
    events = c.collect()
    assert len(events) == 2
    assert {e.dimension for e in events} == {Dimension.INDUSTRY}
    assert events[0].content.startswith("黄金")
    assert "780.5" in events[0].content
    assert events[0].source == "akshare:spot_hist_sge"


def test_single_indicator_failure_isolated():
    ak = MagicMock()
    ak.spot_hist_sge.side_effect = RuntimeError("接口挂了")
    ak.macro_shipping_bdi.return_value = pd.DataFrame(
        {"日期": ["2026-10-29"], "最新值": [2712.0]}
    )
    events = IndustryCollector(ak=ak).collect()
    assert len(events) == 1


def test_empty_df_skipped():
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame({"date": [], "close": []})
    ak.macro_shipping_bdi.return_value = pd.DataFrame(
        {"日期": ["2026-10-29"], "最新值": [2712.0]}
    )
    events = IndustryCollector(ak=ak).collect()
    assert len(events) == 1


def test_nan_value_row_skipped():
    # I4：末行数值为 NaN 时跳过该指标，不产出脏事件
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame(
        {"date": ["2026-10-29"], "close": [float("nan")]}
    )
    ak.macro_shipping_bdi.return_value = pd.DataFrame(
        {"日期": ["2026-10-29"], "最新值": [2712.0]}
    )
    events = IndustryCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].title == "BDI运价"


def test_nan_date_row_skipped():
    # I4：末行日期为 NaN 时同样跳过
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame({"date": [None], "close": [780.5]})
    ak.macro_shipping_bdi.return_value = pd.DataFrame(
        {"日期": ["2026-10-29"], "最新值": [2712.0]}
    )
    events = IndustryCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].title == "BDI运价"


def test_industry_multi_period_series_with_value():
    # 近 10 年逐期存事件（折线图序列），value 为结构化数值
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame(
        {"date": ["2026-10-28", "2026-10-29"], "close": [779.0, 780.5]}
    )
    ak.macro_shipping_bdi.return_value = pd.DataFrame({"日期": [], "最新值": []})
    events = IndustryCollector(ak=ak).collect()
    assert len(events) == 2
    assert [e.value for e in events] == [779.0, 780.5]
    assert events[0].published_at is not None


def test_industry_old_period_filtered_out():
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame(
        {"date": ["2010-01-04"], "close": [300.0]}
    )
    ak.macro_shipping_bdi.return_value = pd.DataFrame({"日期": [], "最新值": []})
    assert IndustryCollector(ak=ak).collect() == []


def test_industry_incremental_since_filters_old_rows():
    # 增量：since 水位线存在时只保留回看窗口内的数据点，旧点不重复产出
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    ak = MagicMock()
    ak.spot_hist_sge.return_value = pd.DataFrame(
        {"date": [recent, "2020-01-02"], "close": [780.5, 350.0]}
    )
    ak.macro_shipping_bdi.return_value = pd.DataFrame({"日期": [], "最新值": []})
    events = IndustryCollector(ak=ak).collect(since=now - timedelta(days=1))
    assert len(events) == 1
    assert events[0].value == 780.5
