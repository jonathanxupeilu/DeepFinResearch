# tests/unit/test_advisor_page.py
"""advisor 页 AppTest 冒烟：Fake pipeline 注入，验证 Agent 轨迹/引用渲染不炸。"""

from streamlit.testing.v1 import AppTest

SCRIPT = """
from app.ui.pages import advisor
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
advisor.render()
"""


def test_advisor_renders_answer_with_trace_and_url_citation(tmp_path):
    script = tmp_path / "advisor_page.py"
    script.write_text(SCRIPT, encoding="utf-8")
    at = AppTest.from_file(str(script), default_timeout=30)
    at.run()
    assert not at.exception

    at.chat_input[0].set_value("什么是护城河？").run()
    assert not at.exception
    rendered = "\n".join(m.value for m in at.markdown)
    assert "护城河是指…… [1]" in rendered
    assert "联网搜索" in rendered  # 决策轨迹里的工具标签
    assert "https://n.cn/1" in rendered  # URL 引用渲染为链接


def test_advisor_first_render_no_exception(tmp_path):
    script = tmp_path / "advisor_page2.py"
    script.write_text(SCRIPT, encoding="utf-8")
    at = AppTest.from_file(str(script), default_timeout=30)
    at.run()
    assert not at.exception
    assert at.title  # 页面标题渲染
