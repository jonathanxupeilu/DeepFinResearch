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
