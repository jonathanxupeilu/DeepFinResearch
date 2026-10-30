# tests/integration/test_monitor_store.py
from datetime import datetime, timezone

from app.monitor.models import Dimension, MonitorEvent
from app.monitor.store import EventStore


def make_event(title: str, dim=Dimension.NEWS, **kwargs) -> MonitorEvent:
    defaults: dict = {
        "dimension": dim,
        "title": title,
        "source": "t",
        "published_at": datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return MonitorEvent(**defaults)


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


def test_hash_field_boundary_no_false_dedup(tmp_path):
    # title/url 边界歧义：旧算法 "ab"+"c" 与 "a"+"bc" 同 hash
    s = EventStore(tmp_path / "m.db")
    added1, _ = s.save_events([make_event("ab", url="c")])
    added2, _ = s.save_events([make_event("a", url="bc")])
    assert added1 == 1 and added2 == 1 and s.count() == 2


def test_hash_includes_dimension(tmp_path):
    # 同 title/url 不同 dimension 视为不同事件
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("same", url="u")])
    added, _ = s.save_events([make_event("same", dim=Dimension.MACRO, url="u")])
    assert added == 1 and s.count() == 2


def test_null_published_at_sorts_last(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events(
        [
            make_event("no_time", published_at=None),
            make_event(
                "late", published_at=datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)
            ),
            make_event(
                "early", published_at=datetime(2026, 10, 30, 8, 0, tzinfo=timezone.utc)
            ),
        ]
    )
    got = s.list_events()
    assert [e.title for e in got] == ["late", "early", "no_time"]


def test_list_limit_pagination(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events(
        [
            make_event(
                f"e{i}", published_at=datetime(2026, 10, 30, 9, i, tzinfo=timezone.utc)
            )
            for i in range(5)
        ]
    )
    got = s.list_events(limit=3)
    assert len(got) == 3 and got[0].title == "e4" and got[-1].title == "e2"
    assert len(s.list_events(limit=100)) == 5


def test_tz_roundtrip(tmp_path):
    s = EventStore(tmp_path / "m.db")
    dt = datetime(2026, 10, 30, 9, 0, tzinfo=timezone.utc)
    s.save_events([make_event("tz", published_at=dt)])
    got = s.list_events()
    assert got[0].published_at.tzinfo is not None
    assert got[0].published_at == dt
    assert got[0].collected_at.tzinfo is not None
