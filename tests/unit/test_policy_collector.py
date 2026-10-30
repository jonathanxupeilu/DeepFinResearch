# tests/unit/test_policy_collector.py
import logging
from datetime import datetime, timedelta
from pathlib import Path

from app.monitor.models import Dimension
from app.monitor.collectors.policy import PolicyCollector


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


def test_meeting_yesterday_in_window(tmp_path):
    recent = datetime.now() - timedelta(hours=12)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, recent))
    events = c.collect()
    assert events and events[0].published_at is not None
    assert events[0].published_at.tzinfo is not None


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
