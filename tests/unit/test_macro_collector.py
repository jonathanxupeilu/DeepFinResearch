# tests/unit/test_macro_collector.py
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.macro import MacroCollector
from app.monitor.models import Dimension


def cpi_df() -> pd.DataFrame:
    return pd.DataFrame({"月份": ["2026年9月份"], "全国-同比增长": [0.4]})


def fake_ak(magic):
    m = magic
    m.macro_china_pmi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "制造业-同比增长": [50.1]}
    )
    m.macro_china_cpi.return_value = cpi_df()
    m.macro_china_shrzgm.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "社会融资规模增量": [30366]}
    )
    return m


def test_macro_collects_one_event_per_indicator():
    c = MacroCollector(ak=fake_ak(MagicMock()))
    events = c.collect()
    assert len(events) == 3
    assert {e.dimension for e in events} == {Dimension.MACRO}
    assert {e.source for e in events} == {
        "akshare:macro_china_pmi",
        "akshare:macro_china_cpi",
        "akshare:macro_china_shrzgm",
    }
    assert "50.1" in events[0].content
    assert "制造业" not in events[0].content  # content 不暴露内部列名


def test_macro_failure_isolated():
    ak = MagicMock()
    ak.macro_china_pmi.side_effect = RuntimeError("接口挂了")
    ak.macro_china_cpi.return_value = cpi_df()
    events = MacroCollector(ak=ak).collect()  # 单指标失败不炸整体
    assert len(events) == 1


def test_macro_empty_df_skipped():
    ak = MagicMock()
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-同比增长": []})
    ak.macro_china_cpi.return_value = cpi_df()
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 1


def test_macro_empty_df_skipped_others_collected():
    ak = MagicMock()
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-同比增长": []})
    ak.macro_china_cpi.return_value = cpi_df()
    ak.macro_china_shrzgm.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "社会融资规模增量": [30366]}
    )
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 2
    assert "30366" in events[-1].content


def test_macro_missing_column_skipped_others_collected():
    ak = MagicMock()
    # PMI 返回缺"制造业-同比增长"列 → 该指标跳过，不崩溃
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": ["2026年9月份"]})
    ak.macro_china_cpi.return_value = cpi_df()
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].title == "CPI"


def test_macro_multi_period_series_with_value():
    # 全历史逐期存事件（折线图序列），value 为结构化数值
    ak = MagicMock()
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份", "2026年8月份"], "全国-同比增长": [0.4, 0.6]}
    )
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-同比增长": []})
    ak.macro_china_shrzgm.return_value = pd.DataFrame(
        {"月份": [], "社会融资规模增量": []}
    )
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 2
    assert [e.value for e in events] == [0.4, 0.6]
    assert events[0].published_at is not None
    assert (events[0].published_at.year, events[0].published_at.month) == (2026, 9)


def test_macro_old_period_filtered_out():
    # 超 10 年的旧期不存（折线图最大期间 10 年，控制 events 膨胀）
    ak = MagicMock()
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2010年1月份"], "全国-同比增长": [1.5]}
    )
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-同比增长": []})
    ak.macro_china_shrzgm.return_value = pd.DataFrame(
        {"月份": [], "社会融资规模增量": []}
    )
    assert MacroCollector(ak=ak).collect() == []
