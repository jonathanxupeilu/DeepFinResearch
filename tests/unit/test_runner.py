# tests/unit/test_runner.py
from unittest.mock import MagicMock

from app.monitor.models import CollectReport, Dimension
from app.monitor.runner import MonitorRunner


def make_runner(collectors):
    store = MagicMock()
    store.save_events.side_effect = lambda evs: (len(evs), 0)
    return MonitorRunner(store=store, collectors=collectors), store


def test_run_all_aggregates_reports():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension, c1.collect = Dimension.NEWS, lambda: [MagicMock()]
    c2.dimension, c2.collect = Dimension.MACRO, lambda: [MagicMock()] * 3
    runner, _ = make_runner([c1, c2])
    reports = runner.run_all()
    assert all(isinstance(r, CollectReport) for r in reports)
    assert [r.added for r in reports] == [1, 3]


def test_single_collector_failure_isolated():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension = Dimension.NEWS
    c1.collect = MagicMock(side_effect=RuntimeError("网络炸了"))
    c2.dimension, c2.collect = Dimension.MACRO, list
    runner, _ = make_runner([c1, c2])
    reports = runner.run_all()
    assert reports[0].ok is False and "网络炸了" in reports[0].error
    assert reports[1].ok is True


def test_error_contains_exception_type():
    c1 = MagicMock()
    c1.dimension = Dimension.NEWS
    c1.collect = MagicMock(side_effect=OSError("disk full"))
    runner, _ = make_runner([c1])
    reports = runner.run_all()
    assert reports[0].ok is False
    assert "OSError" in reports[0].error


def test_save_events_failure_isolated():
    c1, c2 = MagicMock(), MagicMock()
    event_news = MagicMock(dimension=Dimension.NEWS)
    event_macro = MagicMock(dimension=Dimension.MACRO)
    c1.dimension, c1.collect = Dimension.NEWS, lambda: [event_news]
    c2.dimension, c2.collect = Dimension.MACRO, lambda: [event_macro]
    runner, store = make_runner([c1, c2])

    def save_side_effect(evs):
        if evs and evs[0].dimension == Dimension.NEWS:
            raise OSError("disk full")
        return (len(evs), 0)

    store.save_events.side_effect = save_side_effect
    reports = runner.run_all()
    assert reports[0].ok is False
    assert reports[0].added == 0
    assert "disk full" in reports[0].error
    assert reports[1].ok is True
    assert reports[1].added == 1


def test_run_all_empty_collectors():
    runner, _ = make_runner([])
    assert runner.run_all() == []


def test_store_property_returns_injected_store():
    runner, store = make_runner([])
    assert runner.store is store


def test_collect_returns_empty_is_ok():
    c1 = MagicMock()
    c1.dimension, c1.collect = Dimension.NEWS, list
    runner, _ = make_runner([c1])
    reports = runner.run_all()
    assert reports[0].ok is True
    assert reports[0].added == 0
    assert reports[0].error is None
