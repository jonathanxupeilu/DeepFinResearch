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
# GDP 季度累计标签：2026年第1-3季度 → (2026, 3)；2026年第1季度 → (2026, 1)
_GDP_QUARTER_RE = re.compile(r"(\d{4})年第?(\d)(?:-(\d))?季度")
# 折线图最大期间为 10 年，只存近 10 年序列，控制 events 表膨胀
_MAX_HISTORY_YEARS = 10
# 增量采集回看天数：月度数据发布滞后约 1-2 个月，回看 90 天覆盖补发/修订
_SINCE_LOOKBACK_DAYS = 90

# 列名映射集中常量——真实接口列名冒烟时只改这里
_COL_PMI_INDEX = "制造业-指数"
_COL_CPI_YOY = "全国-同比增长"
_COL_CPI_MOM = "全国-环比增长"
_COL_M2_YOY = "货币和准货币(M2)-同比增长"
_COL_M2_MOM = "货币和准货币(M2)-环比增长"
_COL_SHRZGM = "社会融资规模增量"
_COL_GDP_VALUE = "国内生产总值-绝对值"
_COL_GDP_YOY = "国内生产总值-同比增长"
# akshare 的 macro_china_shrzgm 仍走已废弃的 http 端点（405），改直连 https 端点
_SHRZGM_URL = "https://data.mofcom.gov.cn/datamofcom/front/gnmy/shrzgmQuery"


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


def _parse_gdp_quarter(value: Any) -> tuple[int | None, int | None]:
    """解析 GDP 季度累计标签为 (年份, 累计到第几季度)，失败返回 (None, None)。"""
    m = _GDP_QUARTER_RE.search(str(value))
    if not m:
        return None, None
    year = int(m.group(1))
    cum_to = int(m.group(3)) if m.group(3) else int(m.group(2))
    return year, cum_to


def _fetch_shrzgm() -> pd.DataFrame:
    """直连商务部数据中心 https 端点取社融增量（JSON 键 date/tiosfs 对应 月份/增量）。"""
    import httpx

    resp = httpx.post(_SHRZGM_URL, timeout=30.0)
    resp.raise_for_status()
    df = pd.DataFrame(resp.json()).rename(
        columns={"date": "月份", "tiosfs": _COL_SHRZGM}
    )
    return df[["月份", _COL_SHRZGM]]


class MacroCollector(AkshareCollector):
    dimension = Dimension.MACRO

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=365 * _MAX_HISTORY_YEARS)
        if since is not None:
            # 增量更新：只采水位线回看 90 天内的新数据，首次（since=None）仍拉近 10 年全量
            incremental = since - timedelta(days=_SINCE_LOOKBACK_DAYS)
            cutoff = max(cutoff, incremental)
        events: list[MonitorEvent] = []
        # (标题, 接口, 取数列, 接口名字符串, 参考链接)——source 用显式接口名，避免生产/Mock 下命名漂移
        monthly = [
            (
                "PMI",
                self._ak.macro_china_pmi,
                _COL_PMI_INDEX,
                "macro_china_pmi",
                "https://www.stats.gov.cn/",
            ),
            (
                "CPI同比",
                self._ak.macro_china_cpi,
                _COL_CPI_YOY,
                "macro_china_cpi",
                "https://www.stats.gov.cn/",
            ),
            (
                "CPI环比",
                self._ak.macro_china_cpi,
                _COL_CPI_MOM,
                "macro_china_cpi",
                "https://www.stats.gov.cn/",
            ),
            (
                "M2同比",
                self._ak.macro_china_money_supply,
                _COL_M2_YOY,
                "macro_china_money_supply",
                "http://www.pbc.gov.cn/",
            ),
            (
                "M2环比",
                self._ak.macro_china_money_supply,
                _COL_M2_MOM,
                "macro_china_money_supply",
                "http://www.pbc.gov.cn/",
            ),
        ]
        for name, func, column, api_name, url in monthly:
            events.extend(
                self._collect_monthly(name, func, column, api_name, url, cutoff)
            )
        events.extend(self._collect_shrzgm(cutoff))
        events.extend(self._collect_gdp(cutoff))
        return events

    def _collect_monthly(
        self,
        name: str,
        func: Any,
        column: str,
        api_name: str,
        url: str,
        cutoff: datetime,
    ) -> list[MonitorEvent]:
        events: list[MonitorEvent] = []
        try:
            df: pd.DataFrame = self._fetch_or_none(func)
            if not isinstance(df, pd.DataFrame) or df.empty:
                raise ValueError("返回数据非 DataFrame 或为空")
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

    def _collect_shrzgm(self, cutoff: datetime) -> list[MonitorEvent]:
        """社融增量：原始增量 + 同比增速自算（当月 / 上年同月 - 1，上年同月 ≤0 跳过）。

        mofcom 端点只给增量绝对值、无同比列；与 GDP 环比同理，同比由序列自算。
        """
        df: pd.DataFrame | None = self._fetch_or_none(_fetch_shrzgm)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        rows: list[tuple[datetime, float, str]] = []
        for _, row in df.iterrows():
            try:
                raw = row[_COL_SHRZGM]
                if pd.isna(raw):
                    continue
                month_dt = _parse_month(row["月份"])
                if month_dt is None or month_dt < cutoff:
                    continue
                rows.append((month_dt, float(raw), str(row["月份"])))
            except Exception as e:  # noqa: BLE001 单期坏数据只跳过该期
                logger.warning("宏观指标 社融增量 跳过坏期: %s", e)
        if not rows:
            return []
        by_month = {dt: v for dt, v, _ in rows}
        url = "http://www.pbc.gov.cn/"
        events: list[MonitorEvent] = []
        for dt, v, label in rows:
            events.append(
                MonitorEvent(
                    dimension=self.dimension,
                    title="社融增量",
                    source="akshare:macro_china_shrzgm",
                    content=f"社融增量: {v:g}（{label}）",
                    url=url,
                    published_at=dt,
                    value=v,
                )
            )
            prev = by_month.get(datetime(dt.year - 1, dt.month, 1, tzinfo=timezone.utc))
            if prev is not None and prev > 0:
                yoy = (v / prev - 1) * 100
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title="社融增量同比",
                        source="akshare:macro_china_shrzgm",
                        content=f"社融增量同比: {yoy:.2f}%（{label}）",
                        url=url,
                        published_at=dt,
                        value=yoy,
                    )
                )
        return events

    def _collect_gdp(self, cutoff: datetime) -> list[MonitorEvent]:
        """GDP 季度序列：同比取现成列，环比由年初累计值转单季后自算。"""
        df: pd.DataFrame | None = self._fetch_or_none(self._ak.macro_china_gdp)
        if not isinstance(df, pd.DataFrame) or df.empty:
            return []
        # (年份, 累计到第几季度, 累计值, 同比值, 季度末月)
        rows: list[tuple[int, int, float, float | None, datetime]] = []
        for _, row in df.iterrows():
            try:
                year, cum_to = _parse_gdp_quarter(row["季度"])
                if year is None or cum_to is None:
                    continue
                cum_value = row[_COL_GDP_VALUE]
                if pd.isna(cum_value):
                    continue
                quarter_dt = datetime(year, cum_to * 3, 1, tzinfo=timezone.utc)
                if quarter_dt < cutoff:
                    continue
                yoy_raw = row.get(_COL_GDP_YOY)
                yoy = None if pd.isna(yoy_raw) else float(yoy_raw)
                rows.append((year, cum_to, float(cum_value), yoy, quarter_dt))
            except Exception as e:  # noqa: BLE001 单期坏数据只跳过该期
                logger.warning("宏观指标 GDP 跳过坏期: %s", e)
        if not rows:
            return []
        events: list[MonitorEvent] = []
        for year, cum_to, _, yoy, dt in rows:
            if yoy is not None:
                events.append(
                    MonitorEvent(
                        dimension=self.dimension,
                        title="GDP同比",
                        source="akshare:macro_china_gdp",
                        content=f"GDP同比: {yoy}（{year}年Q{cum_to}）",
                        url="https://www.stats.gov.cn/",
                        published_at=dt,
                        value=yoy,
                    )
                )
        # 年初累计值转单季：Q1=累计1，Qk=累计k-累计(k-1)
        years_cum: dict[int, dict[int, float]] = {}
        for year, cum_to, cum_value, _, _ in rows:
            years_cum.setdefault(year, {})[cum_to] = cum_value
        single: dict[tuple[int, int], float | None] = {}
        for year in sorted(years_cum):
            cum = years_cum[year]
            for cum_to in sorted(cum):
                if cum_to == 1:
                    single[(year, cum_to)] = cum[1]
                else:
                    prev = cum.get(cum_to - 1)
                    single[(year, cum_to)] = (
                        cum[cum_to] - prev if prev is not None else None
                    )
        # 环比：按时间序相邻单季相除；缺失季度导致后续环比不可算（prev 置 None）
        prev_single: float | None = None
        for year in sorted(years_cum):
            for cum_to in sorted(years_cum[year]):
                s = single[(year, cum_to)]
                if s is not None and prev_single not in (None, 0):
                    mom = (s / prev_single - 1) * 100
                    dt = datetime(year, cum_to * 3, 1, tzinfo=timezone.utc)
                    events.append(
                        MonitorEvent(
                            dimension=self.dimension,
                            title="GDP环比",
                            source="akshare:macro_china_gdp",
                            content=f"GDP环比: {mom:.2f}（{year}年Q{cum_to}）",
                            url="https://www.stats.gov.cn/",
                            published_at=dt,
                            value=mom,
                        )
                    )
                prev_single = s
        return events
