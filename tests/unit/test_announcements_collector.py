# tests/unit/test_announcements_collector.py
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.announcements import AnnouncementsCollector
from app.monitor.holdings import Holding
from app.monitor.models import Dimension


def make_df(codes):
    return pd.DataFrame(
        {
            "公告日期": ["2026-10-29"] * len(codes),
            "公告标题": ["关于回购股份的公告"] * len(codes),
            "股票代码": codes,
            "公告类型": ["公司公告"] * len(codes),
        }
    )


def test_collects_events_for_holdings():
    ak = MagicMock()
    ak.stock_notice_report.return_value = make_df(["600519", "000858"])
    holdings = [Holding(code="600519", name="贵州茅台")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.ANNOUNCEMENT
    assert events[0].title == "关于回购股份的公告"
    assert events[0].source == "akshare:stock_notice_report"
    assert events[0].published_at is not None


def test_code_with_suffix_normalized():
    ak = MagicMock()
    ak.stock_notice_report.return_value = make_df(["600519.SH", "000858.SZ"])
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1


def test_empty_holdings_no_request():
    ak = MagicMock()
    events = AnnouncementsCollector(holdings=[], ak=ak).collect()
    assert events == []
    ak.stock_notice_report.assert_not_called()


def test_bad_row_skipped():
    ak = MagicMock()
    df = pd.DataFrame(
        {
            "公告日期": ["2026-10-29", None],
            "公告标题": ["正常公告", None],
            "股票代码": ["600519", "600519"],
            "公告类型": ["公司公告", "公司公告"],
        }
    )
    ak.stock_notice_report.return_value = df
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1
