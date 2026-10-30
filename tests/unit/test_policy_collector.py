# tests/unit/test_policy_collector.py
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.monitor.collectors.policy import PolicyCollector
from app.monitor.models import Dimension


def make_calendar(tmp_path: Path, meeting_date: datetime) -> Path:
    f = tmp_path / "cal.json"
    f.write_text(
        f'[{{"date": "{meeting_date:%Y-%m-%d}", "name": "中央经济工作会议"}}]',
        encoding="utf-8",
    )
    return f


def test_upcoming_meeting_within_30_days(tmp_path):
    soon = datetime.now() + timedelta(days=10)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, soon))
    events = c.collect()
    assert events and events[0].dimension == Dimension.POLICY
    assert "中央经济工作会议" in events[0].title


def test_meeting_outside_window_skipped(tmp_path):
    far = datetime.now() + timedelta(days=90)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, far))
    assert c.collect() == []


def _utc_midnight_today() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def test_meeting_today_in_window(tmp_path):
    today = _utc_midnight_today()
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, today))
    events = c.collect()
    assert events and events[0].published_at is not None
    assert events[0].published_at.tzinfo is not None
    assert events[0].published_at == today


def test_meeting_yesterday_out_of_window(tmp_path):
    # 日历只有日期粒度（解析为当日 00:00 UTC），窗口下界为 now-1d（精确到时刻），
    # 因此昨天的会议必然早于下界、不入窗——该行为是确定的。
    yesterday = _utc_midnight_today() - timedelta(days=1)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, yesterday))
    assert c.collect() == []


def test_meeting_plus_30_days_in_window(tmp_path):
    boundary = _utc_midnight_today() + timedelta(days=30)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, boundary))
    assert c.collect()


def test_meeting_plus_31_days_out_of_window(tmp_path):
    beyond = _utc_midnight_today() + timedelta(days=31)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, beyond))
    assert c.collect() == []


def test_missing_calendar_returns_empty(tmp_path, caplog):
    c = PolicyCollector(calendar_path=tmp_path / "nope.json")
    with caplog.at_level(logging.WARNING):
        assert c.collect() == []
    assert any("日历" in r.message for r in caplog.records)


def test_corrupt_calendar_returns_empty(tmp_path, caplog):
    f = tmp_path / "bad.json"
    f.write_text("{not valid json", encoding="utf-8")
    c = PolicyCollector(calendar_path=f)
    with caplog.at_level(logging.WARNING):
        assert c.collect() == []
    assert any("日历" in r.message for r in caplog.records)
