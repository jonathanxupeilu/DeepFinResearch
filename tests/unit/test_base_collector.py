# tests/unit/test_base_collector.py
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pandas as pd

from app.monitor.collectors.base import AkshareCollector


class DummyCollector(AkshareCollector):
    dimension = None  # 测试桩，不需要真实 Dimension


def test_fetch_or_none_timeout_returns_none_quickly():
    # I2：慢接口在 request_timeout 内未返回 → warning + None，近毫秒级返回
    def slow_fn():
        time.sleep(2)
        return pd.DataFrame({"a": [1]})

    collector = DummyCollector(ak=MagicMock(), request_timeout=0.1)
    start = time.monotonic()
    result = collector._fetch_or_none(slow_fn)
    elapsed = time.monotonic() - start
    assert result is None
    assert elapsed < 0.5  # 毫秒级（相对 2s 的 sleep）


def test_fetch_or_none_normal_result_not_timeout():
    def fast_fn():
        return pd.DataFrame({"a": [1]})

    collector = DummyCollector(ak=MagicMock(), request_timeout=5.0)
    result = collector._fetch_or_none(fast_fn)
    assert isinstance(result, pd.DataFrame)


def test_fetch_or_none_exception_returns_none():
    def broken_fn():
        raise RuntimeError("接口挂了")

    collector = DummyCollector(ak=MagicMock())
    assert collector._fetch_or_none(broken_fn) is None


def test_parse_datetime_beijing_naive_to_utc():
    # M2：naive 值按北京时间（Asia/Shanghai）本地化后转 UTC——09:00 北京 → 01:00 UTC
    dt = AkshareCollector._parse_datetime("2026-10-30 09:00")
    assert dt == datetime(2026, 10, 30, 1, 0, tzinfo=timezone.utc)


def test_parse_datetime_bad_value_none():
    assert AkshareCollector._parse_datetime("garbage") is None
    assert AkshareCollector._parse_datetime(None) is None
