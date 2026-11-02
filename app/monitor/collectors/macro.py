# app/monitor/collectors/macro.py
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

_MONTH_RE = re.compile(r"(\d{4})\D+(\d{1,2})")
_COMPACT_MONTH_RE = re.compile(r"^(\d{4})(\d{1,2})$")
# 折线图最大期间为 10 年，只存近 10 年序列，控制 events 表膨胀
_MAX_HISTORY_YEARS = 10


def _parse_month(value: Any) -> datetime | None:
    """解析中文年月（2026年09月份）/ ISO（2026-09）/ 紧凑（202609）为 UTC 月初，失败置 None。"""
    s = str(value).strip()
    m = _MONTH_RE.search(s) or _COMPACT_MONTH_RE.match(s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), 1, tzinfo=timezone.utc)
    except ValueError:
        return None


class MacroCollector(AkshareCollector):
    dimension = Dimension.MACRO

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        # (标题, 接口, 取数列, 接口名字符串, 参考链接)——source 用显式接口名，避免生产/Mock 下命名漂移
        indicators = [
            (
                "PMI",
                self._ak.macro_china_pmi,
                "制造业-同比增长",
                "macro_china_pmi",
                "https://www.stats.gov.cn/",
            ),
            (
                "CPI",
                self._ak.macro_china_cpi,
                "全国-同比增长",
                "macro_china_cpi",
                "https://www.stats.gov.cn/",
            ),
            (
                "社融增量",
                self._ak.macro_china_shrzgm,
                "社会融资规模增量",
                "macro_china_shrzgm",
                "http://www.pbc.gov.cn/",
            ),
        ]
        cutoff = datetime.now(timezone.utc) - timedelta(days=365 * _MAX_HISTORY_YEARS)
        events: list[MonitorEvent] = []
        for name, func, column, api_name, url in indicators:
            try:
                df: pd.DataFrame = self._fetch_or_none(func)
                if not isinstance(df, pd.DataFrame) or df.empty:
                    raise ValueError("返回数据非 DataFrame 或为空")
                # 近 10 年逐期存事件（折线图时间序列）；content_hash 去重保证重复采集不膨胀
                for _, row in df.iterrows():
                    try:
                        raw = row[column]
                        if pd.isna(raw):
                            continue
                        month_dt = _parse_month(row["月份"])
                        if month_dt is None or month_dt < cutoff:
                            continue
                        events.append(
                            MonitorEvent(
                                dimension=self.dimension,
                                title=name,
                                source=f"akshare:{api_name}",
                                content=f"{name}: {raw}（{row['月份']}）",
                                url=url,
                                published_at=month_dt,
                                value=float(raw),
                            )
                        )
                    except Exception as e:  # noqa: BLE001 单期坏数据只跳过该期
                        logger.warning("宏观指标 %s 跳过坏期: %s", name, e)
            except Exception as e:  # noqa: BLE001 单指标失败不炸整体
                logger.warning("宏观指标 %s 采集失败: %s", name, e)
        return events
