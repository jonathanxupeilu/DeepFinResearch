import sys
from pathlib import Path

# streamlit run 会把本文件所在目录插到 sys.path 前面，
# 显式把项目根放到最前，保证 `import app` 解析到项目包
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from app.factory import build_ingest_components, build_pipeline
from app.ingest.loaders import load_file
from app.models import Document, RagAnswer

st.set_page_config(page_title="DeepFinResearch", page_icon="⚙️")
st.title("⚙️ DeepFinResearch · 本地知识库问答")

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
                st.success(f"「{uploaded.name}」入库成功：{index_result.added} 个切片")
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
                result = build_pipeline().answer(question)
            except Exception:  # noqa: BLE001 — UI 兜底，任何生成异常都转为错误提示
                result = None
        if result is None:
            st.error("生成回答失败，请稍后重试")
        else:
            st.markdown(result.answer)
            if result.citations:
                with st.expander("📎 引用来源"):
                    for c in result.citations:
                        st.markdown(f"**[{c.marker}] {c.source}**\n\n> {c.text[:200]}…")
            st.session_state.messages.append(
                {"role": "assistant", "content": result.answer}
            )
