import sys
from hashlib import sha256
from pathlib import Path

# 保证本模块被独立导入时也可解析 app 包
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from app.factory import build_ingest_components, build_monitor_runner
from app.ingest.indexer import IndexResult
from app.models import Document
from app.monitor.holdings import _DEFAULT as HOLDINGS_PATH
from app.monitor.models import CollectReport, Dimension, MonitorEvent

_REPORTS_KEY = "collect_reports"


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
        runner = build_monitor_runner()
        try:
            counts = runner._store.counts_by_dimension()
        finally:
            runner._store.close()
    except Exception:  # noqa: BLE001 — UI 兜底，存储异常转为错误提示
        st.error("读取监控数据失败，请稍后重试")
        return
    cols = st.columns(len(Dimension))
    for col, dim in zip(cols, Dimension):
        col.metric(dim.value, counts.get(dim, 0))  # counts_by_dimension 不含 0 计数维度


def _collect_now() -> None:
    try:
        with st.spinner("正在采集六维度数据…"):
            runner = build_monitor_runner()
            try:
                reports = runner.run_all()
            finally:
                runner._store.close()
    except Exception:  # noqa: BLE001 — UI 兜底，采集异常转为错误提示
        st.error("采集失败，请稍后重试")
        return
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
    digest = sha256(md.encode("utf-8")).hexdigest()[:16]
    doc = Document(source=f"monitor/{e.dimension.value}/{digest}.md", content=md)
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
        runner = build_monitor_runner()
        try:
            events = runner._store.list_events(dim, limit=100)
        finally:
            runner._store.close()
    except Exception:  # noqa: BLE001 — UI 兜底，存储异常转为错误提示
        st.error("读取监控事件失败，请稍后重试")
        return
    if not events:
        st.info("暂无事件，点击上方「🔄 立即采集」试试")
        return
    for i, e in enumerate(events):
        time_str = e.published_at.strftime("%Y-%m-%d %H:%M") if e.published_at else "—"
        with st.expander(f"{time_str}｜{e.dimension.value}｜{e.title}（{e.source}）"):
            st.markdown(e.content or "_无内容_")
            if e.url:
                st.markdown(f"[原文链接]({e.url})")
            if st.button("📥 入库知识库", key=f"ingest-{i}"):
                _ingest_event(e)


def render() -> None:
    st.set_page_config(page_title="市场监控", page_icon="📊")
    st.title("📊 市场监控")

    _show_holdings_hint()
    _show_metrics()

    st.button("🔄 立即采集", on_click=_collect_now)
    _show_reports()

    dim_label = st.selectbox("维度筛选", ["全部"] + [d.value for d in Dimension])
    _show_events(None if dim_label == "全部" else Dimension(dim_label))
