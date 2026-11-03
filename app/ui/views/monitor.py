import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 保证本模块被独立导入时也可解析 app 包
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd  # type: ignore[import-untyped]
import streamlit as st

from app.factory import (
    build_ingest_components,
    build_monitor_runner,
    build_monitor_store,
)
from app.ingest.indexer import IndexResult
from app.models import Document
from app.monitor.holdings import DEFAULT_HOLDINGS_PATH as HOLDINGS_PATH
from app.monitor.models import CollectReport, Dimension, MonitorEvent

_REPORTS_KEY = "collect_reports"
_RETENTION_DAYS = 30  # 事件保留天数：超过自动清理

# 事件类维度（列表展示）与指标类维度（折线图展示）分离
_EVENT_DIMS = [
    Dimension.ANNOUNCEMENT,
    Dimension.NEWS,
    Dimension.FED,
    Dimension.POLICY,
]
_SERIES_DIMS = [Dimension.MACRO, Dimension.INDUSTRY]
# 侧边栏「指标分类」→ 展示维度：宏观经济指标默认，黄金/BDI 归大宗商品指标
_CATEGORY_DIMS = {
    "宏观经济指标": [Dimension.MACRO],
    "大宗商品指标": [Dimension.INDUSTRY],
}
_PERIODS = {"近1年": 365, "近3年": 365 * 3, "近5年": 365 * 5, "近10年": 365 * 10}
# 指标分组：同一指标多口径（同比/环比）合并为一张卡，卡内切换口径
_INDICATOR_GROUPS: dict[Dimension, list[tuple[str, dict[str, str]]]] = {
    Dimension.MACRO: [
        ("GDP", {"同比": "GDP同比", "环比": "GDP环比"}),
        ("CPI", {"同比": "CPI同比", "环比": "CPI环比"}),
        ("M2", {"同比": "M2同比", "环比": "M2环比"}),
        ("PMI", {"指数": "PMI"}),
        ("社融增量", {"同比": "社融增量同比", "增量": "社融增量"}),
    ],
    Dimension.INDUSTRY: [
        ("黄金", {"收盘价": "黄金"}),
        ("BDI运价", {"运价": "BDI运价"}),
    ],
}


def _show_holdings_hint() -> None:
    if HOLDINGS_PATH.exists():
        st.caption(f"持仓配置：{HOLDINGS_PATH}")
    else:
        st.warning(
            f"未找到持仓配置 {HOLDINGS_PATH}，请先创建"
            '（如 [{"code": "600519", "name": "贵州茅台"}]），否则持仓公告维度无数据'
        )


def _show_metrics() -> None:
    try:
        with build_monitor_store() as store:
            counts = store.counts_by_dimension()
    except Exception:  # noqa: BLE001 — UI 兜底，存储异常转为错误提示
        st.error("读取监控数据失败，请稍后重试")
        return
    cols = st.columns(len(_EVENT_DIMS))
    for col, dim in zip(cols, _EVENT_DIMS):
        col.metric(dim.value, counts.get(dim, 0))  # counts_by_dimension 不含 0 计数维度


def _render_indicator_card(
    name: str, variants: dict[str, str], series: dict[str, list[tuple[datetime, float]]]
) -> None:
    """渲染单张指标卡：多口径（同比/环比）卡内切换，单口径直接出图。"""
    labels = list(variants)
    if len(labels) > 1:
        choice = (
            st.segmented_control(
                name, labels, default=labels[0], key=f"indicator_{name}"
            )
            or labels[0]
        )
    else:
        choice = labels[0]
        st.markdown(f"**{name}**")
    title = variants[choice]
    points = series.get(title, [])
    if not points:
        st.caption(f"{name}：暂无数据")
        return
    df = (
        pd.DataFrame(sorted(points, key=lambda p: p[0]), columns=["date", "value"])
        .groupby("date")
        .last()
    )
    st.caption(f"最新 {df['value'].iloc[-1]:,.2f}（{df.index[-1]:%Y-%m-%d}）")
    st.line_chart(df["value"])


def _show_series_charts(dims: list[Dimension]) -> None:
    """指标趋势折线图：按指标分类维度展示，同一指标多口径卡内切换，双列排版。"""
    head_col, period_col = st.columns([4, 1])
    with head_col:
        st.subheader("📈 指标趋势")
    with period_col:
        period = st.selectbox("历史期间", list(_PERIODS), index=0)
    cutoff = datetime.now(timezone.utc) - timedelta(days=_PERIODS[period])
    try:
        with build_monitor_store() as store:
            events = [e for dim in dims for e in store.list_events(dim, limit=10000)]
    except Exception:  # noqa: BLE001 — UI 兜底，存储异常转为错误提示
        st.error("读取指标数据失败，请稍后重试")
        return
    series: dict[str, list[tuple[datetime, float]]] = {}
    for e in events:
        if e.value is None or e.published_at is None or e.published_at < cutoff:
            continue
        series.setdefault(e.title, []).append((e.published_at, e.value))
    groups = [g for dim in dims for g in _INDICATOR_GROUPS[dim]]
    if not any(any(series.get(t) for t in variants.values()) for _, variants in groups):
        st.info("暂无指标数据，点击下方「🔄 立即采集」获取")
        return
    cols = st.columns(2)
    for i, (name, variants) in enumerate(groups):
        with cols[i % 2]:
            _render_indicator_card(name, variants, series)


def _collect_now() -> None:
    reports: list[CollectReport] = []
    purged = 0
    deduped = 0
    try:
        with st.status("正在采集六维度数据…", expanded=True) as status:
            runner = build_monitor_runner()
            try:

                def _on_report(r: CollectReport) -> None:
                    reports.append(r)
                    if r.ok:
                        status.write(f"✅ {r.dimension.value}：新增 {r.added} 条")
                    else:
                        status.write(f"❌ {r.dimension.value}：{r.error}")

                runner.run_all(on_report=_on_report)
                # 存量过时自动清理（指标类序列长期保留，不参与 30 天清理）
                purged = runner.store.purge_before(
                    _RETENTION_DAYS, exclude=_SERIES_DIMS
                )
                # 来源链接上线前的无链接旧版本清理（消除同名重复）
                deduped = runner.store.purge_empty_url()
            finally:
                runner.store.close()
        status.update(label="采集完成", state="complete", expanded=False)
    except Exception:  # noqa: BLE001 — UI 兜底，采集异常转为错误提示
        st.error("采集失败，请稍后重试")
        return
    if purged:
        st.caption(f"🧹 已自动清理 {purged} 条超过 {_RETENTION_DAYS} 天的过期事件")
    if deduped:
        st.caption(f"🧹 已清理 {deduped} 条无来源链接的旧版本重复事件")
    st.session_state[_REPORTS_KEY] = reports


def _show_reports() -> None:
    reports: list[CollectReport] | None = st.session_state.get(_REPORTS_KEY)
    if not reports:
        return
    rows = [
        {
            "维度": r.dimension.value,
            "状态": "✅" if r.ok else "❌",
            "新增条数": r.added,
            "错误原因": r.error or "",
        }
        for r in reports
    ]
    st.dataframe(rows, hide_index=True)
    for r in reports:
        if not r.ok:
            st.error(f"{r.dimension.value} 采集失败：{r.error}")


def _ingest_event(e: MonitorEvent) -> None:
    parts = [f"# {e.title}", e.content, f"来源：{e.source}"]
    if e.url:
        parts.append(f"链接：{e.url}")
    md = "\n\n".join(p for p in parts if p)
    doc = Document(source="", content=md)
    doc.source = f"monitor/{e.dimension.value}/{doc.doc_id}.md"
    try:
        result: IndexResult = build_ingest_components().index_document(doc)
    except Exception:  # noqa: BLE001 — UI 兜底，入库异常转为错误提示
        st.error("入库知识库失败，请稍后重试")
        return
    if result.skipped:
        st.info(f"「{e.title}」内容已入库，跳过")
    else:
        st.success(f"「{e.title}」入库成功：{result.added} 个切片")


def _show_events(dim: Dimension | None) -> None:
    try:
        with build_monitor_store() as store:
            events = store.list_events(dim, limit=100)
    except Exception:  # noqa: BLE001 — UI 兜底，存储异常转为错误提示
        st.error("读取监控事件失败，请稍后重试")
        return
    if not events:
        st.info("暂无事件，点击上方「🔄 立即采集」试试")
        return
    for i, e in enumerate(events):
        time_str = e.published_at.strftime("%Y-%m-%d %H:%M") if e.published_at else "—"
        title = e.title[:40]
        with st.expander(f"{time_str}｜{e.dimension.value}｜{title}（{e.source}）"):
            st.markdown(e.content or "_无内容_")
            if e.url:
                st.markdown(f"[来源链接]({e.url})")
            if st.button(
                "📥 入库知识库",
                key=f"ingest-{e.dimension.value}-{e.collected_at.isoformat()}-{i}",
            ):
                _ingest_event(e)


def render() -> None:
    st.set_page_config(page_title="市场监控", page_icon="📊", layout="wide")
    st.title("📊 市场监控")

    _show_holdings_hint()

    # 指标分类放主内容区左侧（不与折线图争抢侧边栏空间）
    cat_col, chart_col = st.columns([1, 5])
    with cat_col:
        st.subheader("指标分类")
        category = st.radio(
            "指标分类",
            list(_CATEGORY_DIMS),
            index=0,
            label_visibility="collapsed",
        )
    with chart_col:
        _show_series_charts(_CATEGORY_DIMS[category])

    _show_metrics()

    st.button("🔄 立即采集", on_click=_collect_now)
    _show_reports()

    dim_label = st.selectbox("维度筛选", ["全部"] + [d.value for d in _EVENT_DIMS])
    _show_events(None if dim_label == "全部" else Dimension(dim_label))
