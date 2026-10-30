# tests/unit/test_announcements_collector.py
import time
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.announcements import AnnouncementsCollector
from app.monitor.holdings import Holding
from app.monitor.models import Dimension


def make_df(codes):
    # 真实接口 stock_notice_report 列结构
    return pd.DataFrame(
        {
            "代码": codes,
            "名称": ["贵州茅台"] * len(codes),
            "公告标题": ["关于回购股份的公告"] * len(codes),
            "公告类型": ["公司公告"] * len(codes),
            "公告日期": ["2026-10-29"] * len(codes),
            "网址": ["http://example.com/ann.pdf"] * len(codes),
        }
    )


def df_only_today(df):
    """多日窗口语义下，仅今天返回 df，其余天返回空表——隔离单日语义。"""
    today = datetime.now().strftime("%Y%m%d")

    def side_effect(*args, **kwargs):
        if kwargs.get("date") == today:
            return df
        return pd.DataFrame()

    return side_effect


def test_collects_events_for_holdings():
    ak = MagicMock()
    ak.stock_notice_report.side_effect = df_only_today(make_df(["600519", "000858"]))
    holdings = [Holding(code="600519", name="贵州茅台")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.ANNOUNCEMENT
    assert events[0].title == "关于回购股份的公告"
    assert events[0].source == "akshare:stock_notice_report"
    assert events[0].published_at is not None
    assert events[0].url  # url 非空——来自真实接口"网址"列


def test_code_with_suffix_normalized():
    ak = MagicMock()
    ak.stock_notice_report.side_effect = df_only_today(
        make_df(["600519.SH", "000858.SZ"])
    )
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
            "代码": ["600519", "600519"],
            "名称": ["贵州茅台", "贵州茅台"],
            "公告标题": ["正常公告", None],
            "公告类型": ["公司公告", "公司公告"],
            "公告日期": ["2026-10-29", None],
            "网址": ["http://example.com/a.pdf", None],
        }
    )
    ak.stock_notice_report.side_effect = df_only_today(df)
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1


def test_similar_longer_code_not_matched():
    # I1 负例：归一化后须精确相等，"6005191" 不得命中持仓 "600519"
    ak = MagicMock()
    ak.stock_notice_report.side_effect = df_only_today(make_df(["6005191"]))
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert events == []


def test_holding_with_suffix_matches_bare_df_code():
    # I1：持仓带交易所后缀、df 裸码，归一化后应匹配
    ak = MagicMock()
    ak.stock_notice_report.side_effect = df_only_today(make_df(["600519"]))
    holdings = [Holding(code="600519.SH")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1


def test_api_failure_degrades_to_empty():
    ak = MagicMock()
    ak.stock_notice_report.side_effect = RuntimeError("接口挂了")
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert events == []


def test_multi_day_window_queries_each_of_last_7_days():
    # I3：date 是单日参数，须循环近 7 天（含今天）逐日调用
    ak = MagicMock()
    ak.stock_notice_report.return_value = make_df(["600519"])
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert ak.stock_notice_report.call_count == 7
    dates = [c.kwargs["date"] for c in ak.stock_notice_report.call_args_list]
    today = datetime.now().strftime("%Y%m%d")
    oldest = (datetime.now() - timedelta(days=6)).strftime("%Y%m%d")
    assert today in dates
    assert oldest in dates
    assert len(dates) == len(set(dates))
    assert len(events) == 7  # 每个成功日各产出 1 条


def test_single_day_failure_skipped_not_fatal():
    # I3：单日失败只跳过该日，不丢其余日期
    ak = MagicMock()
    bad_date = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")

    def side_effect(*args, **kwargs):
        if kwargs.get("date") == bad_date:
            raise RuntimeError("单日接口挂了")
        return make_df(["600519"])

    ak.stock_notice_report.side_effect = side_effect
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert ak.stock_notice_report.call_count == 7
    assert len(events) == 6


def test_fetch_window_timeout_returns_none_quickly():
    # I2：_fetch_window 逐日调用走 _fetch_or_none 超时保护，慢接口不再拖死采集
    def slow(*args, **kwargs):
        time.sleep(2)
        return make_df(["600519"])

    ak = MagicMock()
    ak.stock_notice_report.side_effect = slow
    holdings = [Holding(code="600519")]
    collector = AnnouncementsCollector(holdings=holdings, ak=ak, request_timeout=0.1)
    start = time.monotonic()
    events = collector.collect()
    elapsed = time.monotonic() - start
    assert events == []
    # 7 天 × 0.1s 超时 + 开销，远小于无超时时的 7 × 2s
    assert elapsed < 3.0


def test_real_structure_url_column_present():
    # 真实接口结构含"网址"列（date 对象公告日期），采集后 url 应取自该列
    ak = MagicMock()
    df = pd.DataFrame(
        {
            "代码": ["600519"],
            "名称": ["贵州茅台"],
            "公告标题": ["回购公告"],
            "公告类型": ["公司公告"],
            "公告日期": [date(2026, 10, 29)],
            "网址": ["https://www.sse.com.cn/disclosure.pdf"],
        }
    )
    ak.stock_notice_report.side_effect = df_only_today(df)
    holdings = [Holding(code="600519")]
    events = AnnouncementsCollector(holdings=holdings, ak=ak).collect()
    assert len(events) == 1
    assert events[0].url == "https://www.sse.com.cn/disclosure.pdf"
    assert events[0].published_at is not None
