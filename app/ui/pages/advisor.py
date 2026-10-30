import sys
from pathlib import Path

# streamlit run 会把本文件所在目录插到 sys.path 前面，
# 显式把项目根放到最前，保证本模块被独立导入时也可解析 app 包
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from app.config import get_settings
from app.factory import build_ingest_components, build_pipeline
from app.ingest.loaders import load_file
from app.models import Document, RagAnswer
from app.retrieval.stats import build_library_stats
from app.retrieval.store import VectorStore


@st.cache_resource
def get_pipeline():
    """会话间复用 pipeline（Chroma 连接/Embedder/LLM 客户端）。

    放在 UI 层而非 factory：factory 还服务 CLI 与测试，须保持框架无关。
    """
    return build_pipeline()


@st.cache_resource
def get_vector_store() -> VectorStore:
    """会话间复用向量库连接（只读统计用途）。"""
    return VectorStore(persist_dir=get_settings().chroma_dir)


def _show_library_card() -> None:
    """RAG 离线仓库概览：存量文章数、分类分布、最新入库。"""
    try:
        stats = build_library_stats(get_vector_store().get_all_metadatas())
    except Exception:  # noqa: BLE001 — UI 兜底，统计异常不影响问答主功能
        return
    if stats.articles == 0:
        return
    with st.container(border=True):
        col1, col2 = st.columns(2)
        col1.metric("📚 存量文章", f"{stats.articles} 篇")
        col2.metric("🧩 切片总数", f"{stats.chunks} 块")
        cats = " · ".join(
            f"{name} ({n})"
            for name, n in sorted(stats.categories.items(), key=lambda kv: -kv[1])
        )
        st.caption(f"分类：{cats or '—'}")
        if stats.latest_title:
            when = (
                f"（{stats.latest_time.strftime('%m-%d %H:%M')}）"
                if stats.latest_time
                else ""
            )
            st.caption(f"🆕 最新入库：《{stats.latest_title}》{when}")


def render() -> None:
    st.set_page_config(page_title="DeepFinResearch", page_icon="⚙️")
    st.title("⚙️ DeepFinResearch · 本地知识库问答")
    _show_library_card()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.header("📚 知识库管理")
        uploaded = st.file_uploader("上传文档", type=["md", "txt", "pdf", "docx"])
        if uploaded and st.button("入库"):
            safe_name = Path(uploaded.name).name  # 剥离目录成分，防路径穿越
            tmp = Path("data/uploads") / safe_name
            tmp.parent.mkdir(parents=True, exist_ok=True)
            try:
                tmp.write_bytes(uploaded.getvalue())
                text = load_file(tmp)
                doc = Document(source=uploaded.name, content=text)
                index_result = build_ingest_components().index_document(doc)
                if index_result.skipped:
                    st.info(f"「{uploaded.name}」内容未变化，已跳过")
                else:
                    st.success(
                        f"「{uploaded.name}」入库成功：{index_result.added} 个切片"
                    )
            except (ValueError, OSError, UnicodeDecodeError) as e:
                st.error(f"入库失败: {e}")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if question := st.chat_input("输入你的问题…"):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("检索知识库并生成回答…"):
                result: RagAnswer | None
                try:
                    result = get_pipeline().answer(question)
                except Exception:  # noqa: BLE001 — UI 兜底，任何生成异常都转为错误提示
                    result = None
            if result is None:
                st.error("生成回答失败，请稍后重试")
            else:
                st.markdown(result.answer)
                if result.citations:
                    with st.expander("📎 引用来源"):
                        for c in result.citations:
                            st.markdown(
                                f"**[{c.marker}] {c.source}**\n\n> {c.text[:200]}…"
                            )
                st.session_state.messages.append(
                    {"role": "assistant", "content": result.answer}
                )
