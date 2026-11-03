# tests/unit/test_macro_collector.py
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.monitor.collectors import macro as macro_mod
from app.monitor.collectors.macro import MacroCollector
from app.monitor.models import Dimension


def month_df(**cols) -> pd.DataFrame:
    return pd.DataFrame({"月份": ["2026年9月份"], **{k: [v] for k, v in cols.items()}})


def gdp_df() -> pd.DataFrame:
    """单季值：2025 各季 100/200/300/400，2026 各季 500/600/700（累计转单季）。"""
    return pd.DataFrame(
        {
            "季度": [
                "2026年第1-3季度",
                "2026年第1-2季度",
                "2026年第1季度",
                "2025年第1-4季度",
                "2025年第1-3季度",
                "2025年第1-2季度",
                "2025年第1季度",
            ],
            "国内生产总值-绝对值": [1800, 1100, 500, 1000, 600, 300, 100],
            "国内生产总值-同比增长": [5.0, 5.1, 5.2, 4.0, 4.1, 4.2, 4.3],
        }
    )


@pytest.fixture(autouse=True)
def _mock_shrzgm(monkeypatch):
    """社融接口走模块级 httpx 直连，单测统一打桩默认返回两月增量（供同比自算）。"""
    monkeypatch.setattr(
        macro_mod,
        "_fetch_shrzgm",
        lambda: pd.DataFrame(
            {
                "月份": ["2026年9月份", "2025年9月份"],
                "社会融资规模增量": [30366, 20000],
            }
        ),
    )


def fake_ak(m) -> MagicMock:
    m.macro_china_pmi.return_value = month_df(**{"制造业-指数": 49.8})
    m.macro_china_cpi.return_value = month_df(
        **{"全国-同比增长": 0.4, "全国-环比增长": 0.2}
    )
    m.macro_china_money_supply.return_value = month_df(
        **{"货币和准货币(M2)-同比增长": 7.2, "货币和准货币(M2)-环比增长": 0.79}
    )
    m.macro_china_gdp.return_value = gdp_df()
    return m


def test_macro_collects_all_series_titles():
    c = MacroCollector(ak=fake_ak(MagicMock()))
    events = c.collect()
    assert {e.title for e in events} == {
        "GDP同比",
        "GDP环比",
        "CPI同比",
        "CPI环比",
        "PMI",
        "M2同比",
        "M2环比",
        "社融增量",
        "社融增量同比",
    }
    assert {e.dimension for e in events} == {Dimension.MACRO}


def test_pmi_uses_index_column():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    pmi = [e for e in events if e.title == "PMI"]
    assert len(pmi) == 1
    assert pmi[0].value == 49.8
    assert "制造业" not in pmi[0].content  # content 不暴露内部列名


def test_cpi_produces_yoy_and_mom():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    cpi = {e.title: e.value for e in events if e.title.startswith("CPI")}
    assert cpi == {"CPI同比": 0.4, "CPI环比": 0.2}


def test_m2_produces_yoy_and_mom():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    m2 = {e.title: e.value for e in events if e.title.startswith("M2")}
    assert m2["M2同比"] == 7.2
    assert m2["M2环比"] == pytest.approx(0.79)


def test_shrzgm_produces_increment_and_yoy():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    raw = {e.value for e in events if e.title == "社融增量"}
    assert raw == {30366.0, 20000.0}
    yoy = [e for e in events if e.title == "社融增量同比"]
    assert len(yoy) == 1
    assert yoy[0].value == pytest.approx((30366 / 20000 - 1) * 100)  # 51.83%
    assert yoy[0].published_at == datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_shrzgm_yoy_skips_non_positive_base(monkeypatch):
    monkeypatch.setattr(
        macro_mod,
        "_fetch_shrzgm",
        lambda: pd.DataFrame(
            {
                "月份": ["2025年4月份", "2024年4月份"],
                "社会融资规模增量": [9000, -658],
            }
        ),
    )
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    assert len([e for e in events if e.title == "社融增量"]) == 2
    # 2024-04 基数 -658 ≤ 0，2025-04 不产同比
    assert not any(e.title == "社融增量同比" for e in events)


def test_gdp_yoy_uses_yoy_column():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    gdp_yoy = sorted(
        (e for e in events if e.title == "GDP同比"), key=lambda e: e.published_at
    )
    assert [e.value for e in gdp_yoy] == [4.3, 4.2, 4.1, 4.0, 5.2, 5.1, 5.0]


def test_gdp_mom_computed_from_cumulative():
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    gdp_mom = sorted(
        (e for e in events if e.title == "GDP环比"), key=lambda e: e.published_at
    )
    # 单季 100/200/300/400/500/600/700 → 环比 100/50/33.33/25/20/16.67 %
    assert [round(e.value, 2) for e in gdp_mom] == [
        pytest.approx(100.0),
        pytest.approx(50.0),
        pytest.approx(33.33),
        pytest.approx(25.0),
        pytest.approx(20.0),
        pytest.approx(16.67),
    ]
    # 2026Q1 环比 = 500/400 - 1 = 25%
    assert gdp_mom[3].value == pytest.approx(25.0)
    assert gdp_mom[3].published_at == datetime(2026, 3, 1, tzinfo=timezone.utc)


def test_gdp_first_quarter_has_no_mom():
    # 数据最早季度（2025Q1）无上季可比，不产环比
    events = MacroCollector(ak=fake_ak(MagicMock())).collect()
    gdp_mom = [e for e in events if e.title == "GDP环比"]
    dates = [e.published_at for e in gdp_mom]
    assert datetime(2025, 3, 1, tzinfo=timezone.utc) not in dates


def test_macro_failure_isolated(monkeypatch):
    def boom() -> pd.DataFrame:
        raise RuntimeError("接口挂了")

    monkeypatch.setattr(macro_mod, "_fetch_shrzgm", boom)
    ak = MagicMock()
    ak.macro_china_pmi.side_effect = RuntimeError("接口挂了")
    ak.macro_china_cpi.return_value = month_df(
        **{"全国-同比增长": 0.4, "全国-环比增长": 0.2}
    )
    ak.macro_china_money_supply.side_effect = RuntimeError("接口挂了")
    ak.macro_china_gdp.side_effect = RuntimeError("接口挂了")
    events = MacroCollector(ak=ak).collect()
    assert {e.title for e in events} == {"CPI同比", "CPI环比"}


def test_macro_old_period_filtered_out(monkeypatch):
    monkeypatch.setattr(
        macro_mod,
        "_fetch_shrzgm",
        lambda: pd.DataFrame({"月份": [], "社会融资规模增量": []}),
    )
    ak = MagicMock()
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2010年1月份"], "全国-同比增长": [1.5], "全国-环比增长": [0.1]}
    )
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-指数": []})
    ak.macro_china_money_supply.return_value = pd.DataFrame({"月份": []})
    ak.macro_china_gdp.return_value = pd.DataFrame(
        {"季度": [], "国内生产总值-绝对值": [], "国内生产总值-同比增长": []}
    )
    assert MacroCollector(ak=ak).collect() == []


def test_macro_incremental_since_filters_old_rows(monkeypatch):
    monkeypatch.setattr(
        macro_mod,
        "_fetch_shrzgm",
        lambda: pd.DataFrame({"月份": [], "社会融资规模增量": []}),
    )
    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=30)
    ak = MagicMock()
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {
            "月份": [recent.strftime("%Y年%m月份"), "2020年1月份"],
            "全国-同比增长": [0.4, 1.5],
            "全国-环比增长": [0.2, 0.1],
        }
    )
    ak.macro_china_pmi.return_value = pd.DataFrame({"月份": [], "制造业-指数": []})
    ak.macro_china_money_supply.return_value = pd.DataFrame({"月份": []})
    ak.macro_china_gdp.return_value = pd.DataFrame(
        {"季度": [], "国内生产总值-绝对值": [], "国内生产总值-同比增长": []}
    )
    events = MacroCollector(ak=ak).collect(since=now - timedelta(days=1))
    assert {e.title for e in events} == {"CPI同比", "CPI环比"}
    assert [e.value for e in events if e.title == "CPI同比"] == [0.4]
