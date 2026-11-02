# app/monitor/collectors/industry.py
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd  # type: ignore[import-untyped]

from app.monitor.collectors.base import AkshareCollector
from app.monitor.models import Dimension, MonitorEvent

logger = logging.getLogger(__name__)

# 列名映射集中常量——真实接口列名冒烟时只改这里
_SGE_DATE_COL = "date"
_SGE_CLOSE_COL = "close"
_BDI_DATE_COL = "日期"
_BDI_CLOSE_COL = "最新值"
# 折线图最大期间为 10 年，只存近 10 年序列，控制 events 表膨胀
_MAX_HISTORY_YEARS = 10
# 增量采集回看天数：覆盖数据源补发/修订，重叠部分由 content_hash 去重
_SINCE_LOOKBACK_DAYS = 90


class IndustryCollector(AkshareCollector):
    dimension = Dimension.INDUSTRY

    def collect(self, since: datetime | None = None) -> list[MonitorEvent]:
        # (标题, 接口, 日期列, 数值列, 接口名字符串, 参考链接)
        indicators = [
            (
                "黄金",
                self._ak.spot_hist_sge,
                _SGE_DATE_COL,
                _SGE_CLOSE_COL,
                "spot_hist_sge",
                "https://www.sge.com.cn/",
            ),
            (
                "BDI运价",
                self._ak.macro_shipping_bdi,
                _BDI_DATE_COL,
                _BDI_CLOSE_COL,
                "macro_shipping_bdi",
                "https://www.balticexchange.com/",
            ),
        ]
        cutoff = datetime.now(timezone.utc) - timedelta(days=365 * _MAX_HISTORY_YEARS)
        if since is not None:
            # 增量更新：只采水位线回看 90 天内的新数据，首次（since=None）仍拉近 10 年全量
            incremental = since - timedelta(days=_SINCE_LOOKBACK_DAYS)
            cutoff = max(cutoff, incremental)
        events: list[MonitorEvent] = []
        for name, func, date_col, value_col, api_name, url in indicators:
            try:
                df: pd.DataFrame = self._fetch_or_none(func)
                if not isinstance(df, pd.DataFrame) or df.empty:
                    raise ValueError("返回数据非 DataFrame 或为空")
                # 近 10 年逐期存事件（折线图时间序列）；content_hash 去重保证重复采集不膨胀
                for _, row in df.iterrows():
                    try:
                        if pd.isna(row[date_col]) or pd.isna(row[value_col]):
                            continue
                        date_dt = self._parse_datetime(row[date_col])
                        if date_dt is None or date_dt < cutoff:
                            continue
                        events.append(
                            MonitorEvent(
                                dimension=self.dimension,
                                title=name,
                                source=f"akshare:{api_name}",
                                content=f"{name}: {row[value_col]}（{row[date_col]}）",
                                url=url,
                                published_at=date_dt,
                                value=float(row[value_col]),
                            )
                        )
                    except Exception as e:  # noqa: BLE001 单期坏数据只跳过该期
                        logger.warning("行业指标 %s 跳过坏期: %s", name, e)
            except Exception as e:  # noqa: BLE001 单指标失败不炸整体
                logger.warning("行业指标 %s 采集失败: %s", name, e)
        return events
