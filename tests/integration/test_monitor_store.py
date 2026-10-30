# tests/integration/test_monitor_store.py
from datetime import datetime

from app.monitor.models import Dimension, MonitorEvent
from app.monitor.store import EventStore


def make_event(title: str, dim=Dimension.NEWS) -> MonitorEvent:
    return MonitorEvent(dimension=dim, title=title, source="t",
                        published_at=datetime(2026, 10, 30, 9, 0))


def test_save_and_count(tmp_path):
    s = EventStore(tmp_path / "m.db")
    added, _ = s.save_events([make_event("a"), make_event("b")])
    assert added == 2 and s.count() == 2


def test_hash_dedup(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("同一事件")])
    added, skipped = s.save_events([make_event("同一事件")])
    assert added == 0 and skipped == 1 and s.count() == 1


def test_list_filter_by_dimension_desc(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("n1"), make_event("m1", Dimension.MACRO)])
    got = s.list_events(dimension=Dimension.MACRO)
    assert len(got) == 1 and got[0].title == "m1"


def test_counts_by_dimension(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("a"), make_event("b", Dimension.FED)])
    counts = s.counts_by_dimension()
    assert counts[Dimension.NEWS] == 1 and counts[Dimension.FED] == 1
