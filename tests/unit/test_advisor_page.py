# tests/unit/test_advisor_page.py
"""advisor 页 AppTest 冒烟：Fake pipeline 注入，验证 Agent 轨迹/引用渲染不炸。"""

from streamlit.testing.v1 import AppTest

SCRIPT = """
import os
from pathlib import Path

from app.chat_store import ChatStore
from app.ui.views import advisor
from app.models import Citation, RagAnswer, TraceStep


class FakePipeline:
    def answer(self, question):
        return RagAnswer(
            answer="护城河是指…… [1]",
            citations=[Citation(marker=1, source="https://n.cn/1", text="联网片段")],
            trace=[
                TraceStep(
                    step=1,
                    tool="web_search",
                    arguments={"query": "护城河"},
                    observation="1 条证据",
                )
            ],
        )


advisor.get_pipeline = lambda: FakePipeline()


def _no_store():
    raise RuntimeError("测试环境无向量库")


advisor.get_vector_store = _no_store
advisor.get_chat_store = lambda: ChatStore(Path(os.environ["CHAT_STORE_PATH"]))
advisor.render()
"""


def _make_at(tmp_path, monkeypatch) -> AppTest:
    monkeypatch.setenv("CHAT_STORE_PATH", str(tmp_path / "chat.json"))
    script = tmp_path / "advisor_page.py"
    script.write_text(SCRIPT, encoding="utf-8")
    return AppTest.from_file(str(script), default_timeout=30)


def test_advisor_renders_answer_with_trace_and_url_citation(tmp_path, monkeypatch):
    at = _make_at(tmp_path, monkeypatch)
    at.run()
    assert not at.exception

    at.chat_input[0].set_value("什么是护城河？").run()
    assert not at.exception
    rendered = "\n".join(m.value for m in at.markdown)
    assert "护城河是指…… [1]" in rendered
    assert "联网搜索" in rendered  # 决策轨迹里的工具标签
    assert "https://n.cn/1" in rendered  # URL 引用渲染为链接


def test_advisor_first_render_no_exception(tmp_path, monkeypatch):
    at = _make_at(tmp_path, monkeypatch)
    at.run()
    assert not at.exception
    assert at.title  # 页面标题渲染


def test_advisor_history_saved_and_resumable(tmp_path, monkeypatch):
    from app.chat_store import ChatStore

    store_path = tmp_path / "chat.json"
    at = _make_at(tmp_path, monkeypatch)
    at.run()
    assert not at.exception
    assert any(b.label == "➕ 新对话" for b in at.button)  # 历史对话面板存在

    at.chat_input[0].set_value("什么是护城河？").run()
    assert not at.exception
    sessions = ChatStore(store_path).list_sessions()
    assert len(sessions) == 1
    assert sessions[0].title == "什么是护城河？"
    assert [m.role for m in sessions[0].messages] == ["user", "assistant"]

    next(b for b in at.button if b.label == "➕ 新对话").click().run()
    assert not at.exception
    assert not at.session_state.messages  # 新对话清空当前上下文

    next(b for b in at.button if b.label == "什么是护城河？").click().run()
    assert not at.exception
    rendered = "\n".join(m.value for m in at.markdown)
    assert "什么是护城河？" in rendered  # 上轮问答重新载入可续聊
    assert "护城河是指…… [1]" in rendered
