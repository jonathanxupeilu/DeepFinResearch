# app/monitor/collectors/base.py
from typing import Protocol, runtime_checkable

from app.monitor.models import Dimension, MonitorEvent


@runtime_checkable
class Collector(Protocol):
    dimension: Dimension

    def collect(self) -> list[MonitorEvent]: ...
