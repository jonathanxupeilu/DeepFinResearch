# app/monitor/collectors/policy.py
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.monitor.models import Dimension, MonitorEvent

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CALENDAR = _PROJECT_ROOT / "config" / "policy_calendar.json"

logger = logging.getLogger(__name__)


class PolicyCollector:
    dimension = Dimension.POLICY

    def __init__(self, calendar_path: Path = _DEFAULT_CALENDAR) -> None:
        self.calendar_path = calendar_path

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        try:
            data = json.loads(self.calendar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("重大会议日历不可用（%s）：%s", self.calendar_path, e)
            return []

        now = datetime.now(timezone.utc)
        low = now - timedelta(days=1)
        high = now + timedelta(days=30)
        events: list[MonitorEvent] = []
        for item in data:
            # 逐条容错：坏条目（缺字段/坏日期）warning 跳过，不丢其余条目
            try:
                date = datetime.strptime(item["date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if low <= date <= high:
                    name = item["name"]
                    events.append(
                        MonitorEvent(
                            dimension=self.dimension,
                            title=f"临近：{name}（{item['date']}）",
                            content=f"重大会议：{name}，日期 {item['date']}。",
                            source="policy_calendar",
                            published_at=date,
                        )
                    )
            except (KeyError, TypeError, ValueError) as e:
                logger.warning("跳过坏条目: %s", e)
        return events
