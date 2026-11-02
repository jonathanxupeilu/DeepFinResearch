# app/tools/current_time.py
"""当前时间工具：Agent 自主获取"现在几点"，用于解析「最近/今天」等时间词。"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.pipeline.prompts import CURRENT_TIME_DESCRIPTION
from app.tools.base import ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_BEIJING_OFFSET = timedelta(hours=8)  # UTC+8，不依赖系统时区库
_WEEKDAYS = "一二三四五六日"

_SPEC = ToolSpec(
    name="current_time",
    description=CURRENT_TIME_DESCRIPTION,
    parameters={"type": "object", "properties": {}},
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CurrentTimeTool:
    spec = _SPEC

    def __init__(self, now_fn: Callable[[], datetime] = _utc_now) -> None:
        self._now_fn = now_fn  # 返回 UTC 当前时间，北京时间换算由本工具完成

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        now = self._now_fn() + _BEIJING_OFFSET
        weekday = _WEEKDAYS[now.weekday()]
        return ToolResult(text=f"当前北京时间：{now:%Y-%m-%d %H:%M}（星期{weekday}）")
