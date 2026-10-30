# app/monitor/collectors/base.py
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)


@runtime_checkable
class Collector(Protocol):
    dimension: Dimension

    def collect(self) -> list[MonitorEvent]: ...


class AkshareCollector:
    """akshare 采集器公共基类：ak 注入、防抖取数、日期解析、空值判断。"""

    dimension: Dimension

    def __init__(self, ak: Any = None) -> None:
        if ak is None:
            import akshare  # type: ignore[import-untyped]

            ak = akshare
        self._ak: Any = ak

    def _fetch_or_none(
        self, fn: Callable[..., pd.DataFrame], *args: Any, **kwargs: Any
    ) -> pd.DataFrame | None:
        """调用 akshare 接口，异常时 warning 并降级为 None。"""
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 接口异常降级为空结果
            logger.warning(
                "akshare 接口 %s 调用失败: %s", getattr(fn, "__name__", fn), e
            )
            return None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """解析任意日期/时间值为 UTC datetime，失败置 None。"""
        try:
            if pd.isna(value):
                return None
            return pd.to_datetime(value, utc=True).to_pydatetime()
        except Exception:  # noqa: BLE001 日期解析易错，失败置 None
            return None

    @staticmethod
    def _not_blank(value: Any) -> bool:
        """判断单元格值是否为有效非空文本（NaN/空串/纯空白均视为空）。"""
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            return False
        return bool(str(value).strip())
