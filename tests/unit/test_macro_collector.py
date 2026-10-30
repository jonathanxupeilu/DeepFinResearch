# tests/unit/test_macro_collector.py
import pandas as pd

from app.monitor.models import Dimension
from app.monitor.collectors.macro import MacroCollector


def fake_ak(magic):
    m = magic
    m.macro_china_pmi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "制造业-同比增长": [50.1]}
    )
    m.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    return m


def test_macro_collects_one_event_per_indicator():
    from unittest.mock import MagicMock
    c = MacroCollector(ak=fake_ak(MagicMock()))
    events = c.collect()
    assert len(events) == 2
    assert {e.dimension for e in events} == {Dimension.MACRO}
    assert "50.1" in events[0].content


def test_macro_failure_isolated():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.macro_china_pmi.side_effect = RuntimeError("接口挂了")
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    events = MacroCollector(ak=ak).collect()  # 单指标失败不炸整体
    assert len(events) == 1


def test_macro_empty_df_skipped():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.macro_china_pmi.return_value = pd.DataFrame(
        {"月份": [], "制造业-同比增长": []}
    )
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 1


def test_macro_empty_df_failure_also_isolated():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.macro_china_pmi.return_value = pd.DataFrame(
        {"月份": [], "制造业-同比增长": []}
    )
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    ak.macro_china_shrzgm.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "当月值": [30366]}
    )
    events = MacroCollector(ak=ak).collect()
    assert len(events) == 2
    assert "30366" in events[-1].content
