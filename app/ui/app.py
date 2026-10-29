from pathlib import Path

import streamlit as st

from app.factory import build_ingest_components, build_pipeline
from app.ingest.loaders import load_file
from app.models import Document

st.set_page_config(page_title="DeepFinResearch", page_icon="⚙️")
st.title("⚙️ DeepFinResearch · 本地知识库问答")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("📚 知识库管理")
    uploaded = st.file_uploader("上传文档", type=["md", "txt", "pdf", "docx"])
    if uploaded and st.button("入库"):
        tmp = Path("data/uploads") / uploaded.name
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(uploaded.getvalue())
        try:
            text = load_file(tmp)
            doc = Document(source=uploaded.name, content=text)
            result = build_ingest_components().index_document(doc)
            if result.skipped:
                st.info(f"「{uploaded.name}」内容未变化，已跳过")
            else:
                st.success(f"「{uploaded.name}」入库成功：{result.added} 个切片")
        except ValueError as e:
            st.error(str(e))

    if st.button("刷新文档列表"):
        st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("输入你的问题…"):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("检索知识库并生成回答…"):
            result = build_pipeline().answer(question)
        st.markdown(result.answer)
        if result.citations:
            with st.expander("📎 引用来源"):
                for c in result.citations:
                    st.markdown(f"**[{c.marker}] {c.source}**\n\n> {c.text[:200]}…")
    st.session_state.messages.append({"role": "assistant", "content": result.answer})
