# tests/unit/test_runner.py
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.monitor.models import CollectReport, Dimension
from app.monitor.runner import MonitorRunner


def make_runner(collectors):
    store = MagicMock()
    store.save_events.side_effect = lambda evs: (len(evs), 0)
    store.get_last_collect.return_value = None
    return MonitorRunner(store=store, collectors=collectors), store


def test_run_all_aggregates_reports():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension, c1.collect = Dimension.NEWS, lambda since=None: [MagicMock()]
    c2.dimension, c2.collect = Dimension.MACRO, lambda since=None: [MagicMock()] * 3
    runner, _ = make_runner([c1, c2])
    reports = runner.run_all()
    assert all(isinstance(r, CollectReport) for r in reports)
    assert [r.added for r in reports] == [1, 3]


def test_single_collector_failure_isolated():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension = Dimension.NEWS
    c1.collect = MagicMock(side_effect=RuntimeError("网络炸了"))
    c2.dimension, c2.collect = Dimension.MACRO, lambda since=None: []
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
    c1.dimension, c1.collect = Dimension.NEWS, lambda since=None: [event_news]
    c2.dimension, c2.collect = Dimension.MACRO, lambda since=None: [event_macro]
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
    c1.dimension, c1.collect = Dimension.NEWS, lambda since=None: []
    runner, _ = make_runner([c1])
    reports = runner.run_all()
    assert reports[0].ok is True
    assert reports[0].added == 0
    assert reports[0].error is None


def test_reports_preserve_collector_order_under_parallel():
    # A：并行执行下 reports 仍按注入顺序返回，快源不等慢源也不改变顺序
    c_slow, c_fast = MagicMock(), MagicMock()
    c_slow.dimension = Dimension.NEWS

    def slow_collect(since=None):
        time.sleep(0.15)
        return [MagicMock()]

    c_slow.collect = slow_collect
    c_fast.dimension, c_fast.collect = Dimension.MACRO, lambda since=None: []
    runner, _ = make_runner([c_slow, c_fast])
    reports = runner.run_all()
    assert [r.dimension for r in reports] == [Dimension.NEWS, Dimension.MACRO]


def test_run_all_passes_since_from_store():
    # B：runner 从 store 读每维度上次采集时间，作为 since 传给采集器
    last = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension = Dimension.NEWS
    c1.collect = MagicMock(return_value=[])
    c2.dimension = Dimension.MACRO
    c2.collect = MagicMock(return_value=[])
    runner, store = make_runner([c1, c2])
    store.get_last_collect.side_effect = (
        lambda d: last if d == Dimension.NEWS else None
    )
    runner.run_all()
    c1.collect.assert_called_once_with(last)
    c2.collect.assert_called_once_with(None)


def test_on_report_callback_invoked_per_dimension():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension, c1.collect = Dimension.NEWS, lambda since=None: []
    c2.dimension, c2.collect = Dimension.MACRO, lambda since=None: []
    runner, _ = make_runner([c1, c2])
    seen: list[CollectReport] = []
    runner.run_all(on_report=seen.append)
    assert len(seen) == 2
    assert {r.dimension for r in seen} == {Dimension.NEWS, Dimension.MACRO}


def test_updates_last_collect_on_success_only():
    # B：采集成功才推进该维度的水位线，失败维度下次重采
    c_ok, c_bad = MagicMock(), MagicMock()
    c_ok.dimension, c_ok.collect = Dimension.NEWS, lambda since=None: []
    c_bad.dimension = Dimension.MACRO
    c_bad.collect = MagicMock(side_effect=RuntimeError("挂了"))
    runner, store = make_runner([c_ok, c_bad])
    runner.run_all()
    updated = {call.args[0] for call in store.set_last_collect.call_args_list}
    assert updated == {Dimension.NEWS}
