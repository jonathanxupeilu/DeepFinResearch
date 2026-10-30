# -*- coding: utf-8 -*-
"""临时探针：逐个 collector 真实采集，报告各维度产出。"""
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

from app.monitor.collectors.announcements import AnnouncementsCollector
from app.monitor.collectors.fed import FedCollector
from app.monitor.collectors.industry import IndustryCollector
from app.monitor.collectors.macro import MacroCollector
from app.monitor.collectors.news import NewsCollector
from app.monitor.holdings import Holding


def report(name, collector):
    print(f"\n===== {name} =====", flush=True)
    try:
        events = collector.collect()
        print(f"[{name}] 事件数: {len(events)}", flush=True)
        for e in events[:5]:
            print(
                f"  - title={e.title!r} source={e.source!r} url={e.url!r} "
                f"published_at={e.published_at} content={e.content[:80]!r}",
                flush=True,
            )
        if len(events) > 5:
            print(f"  ...(共 {len(events)} 条)", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] 采集异常: {exc!r}", flush=True)


report("AnnouncementsCollector(600519)", AnnouncementsCollector([Holding(code="600519", name="贵州茅台")]))
report("MacroCollector", MacroCollector())
report("NewsCollector", NewsCollector())
report("FedCollector", FedCollector())
report("IndustryCollector", IndustryCollector())
print("\nDONE", flush=True)
sys.exit(0)
