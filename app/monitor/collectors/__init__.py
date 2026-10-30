# app/monitor/collectors/__init__.py
from app.monitor.collectors.announcements import AnnouncementsCollector
from app.monitor.collectors.fed import FedCollector
from app.monitor.collectors.industry import IndustryCollector
from app.monitor.collectors.macro import MacroCollector
from app.monitor.collectors.news import NewsCollector
from app.monitor.collectors.policy import PolicyCollector

__all__ = [
    "AnnouncementsCollector",
    "FedCollector",
    "IndustryCollector",
    "MacroCollector",
    "NewsCollector",
    "PolicyCollector",
]
