# tests/unit/test_monitor_models.py
import pytest
from pydantic import ValidationError

from app.monitor.models import CollectReport, Dimension, MonitorEvent


def test_dimension_has_six_values():
    assert {d.value for d in Dimension} == {
        "持仓公告",
        "每日要闻",
        "宏观指标",
        "美联储",
        "重大会议",
        "行业指标",
    }


def test_monitor_event_auto_collected_at():
    e = MonitorEvent(dimension=Dimension.NEWS, title="央行降准", source="cls")
    assert e.collected_at is not None
    assert e.content == "" and e.url == ""


def test_monitor_event_requires_title_and_source():
    with pytest.raises(ValidationError):
        MonitorEvent(dimension=Dimension.NEWS, title="", source="cls")


def test_collect_report_defaults():
    r = CollectReport(dimension=Dimension.MACRO, ok=True, added=3)
    assert r.error is None
