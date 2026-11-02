# tests/unit/test_current_time_tool.py
from datetime import datetime, timezone

from app.tools.current_time import CurrentTimeTool


def test_spec_shape():
    spec = CurrentTimeTool().spec
    assert spec.name == "current_time"
    assert spec.parameters == {"type": "object", "properties": {}}
    assert "时间" in spec.description


def test_run_returns_beijing_time_with_weekday():
    fixed = datetime(
        2026, 11, 2, 6, 30, tzinfo=timezone.utc
    )  # UTC 06:30 → 北京 14:30 星期一
    tool = CurrentTimeTool(now_fn=lambda: fixed)
    result = tool.run({})
    assert result.evidence == []
    assert "2026-11-02 14:30" in result.text
    assert "星期一" in result.text
    assert "北京时间" in result.text


def test_default_clock_returns_naive_safe_now():
    result = CurrentTimeTool().run({})
    assert "北京时间" in result.text
