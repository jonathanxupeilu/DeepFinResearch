# tests/unit/test_cli.py
from unittest.mock import MagicMock

from app.cli import format_answer, run
from app.models import Citation, RagAnswer


def _mock_pipeline(answer: str, citations: list[Citation] | None = None) -> MagicMock:
    p = MagicMock()
    p.answer.return_value = RagAnswer(answer=answer, citations=citations or [])
    return p


def test_format_answer_with_citations():
    result = RagAnswer(
        answer="结论 [1]", citations=[Citation(marker=1, source="a.md", text="片段")]
    )
    text = format_answer(result)
    assert "结论 [1]" in text
    assert "[1] a.md" in text


def test_format_answer_no_citations():
    assert format_answer(RagAnswer(answer="纯回复")) == "纯回复"


def test_run_repl_loop():
    pipeline = _mock_pipeline("回答内容")
    inputs = iter(["什么是护城河？", "/exit"])
    out: list[str] = []
    run(pipeline, input_fn=lambda _: next(inputs), output=out.append)
    pipeline.answer.assert_called_once_with("什么是护城河？")
    assert any("回答内容" in line for line in out)


def test_run_ignores_blank_and_eof():
    pipeline = _mock_pipeline("x")
    inputs = iter(["", "  "])  # 空输入后 EOF
    out: list[str] = []
    run(
        pipeline, input_fn=lambda _: next(inputs), output=out.append
    )  # EOFError 正常退出
    pipeline.answer.assert_not_called()


def test_run_exit_aliases():
    pipeline = _mock_pipeline("x")
    for alias in ("/exit", "/quit", "exit", "q"):
        inputs = iter([alias])
        out: list[str] = []
        run(pipeline, input_fn=lambda _, src=inputs: next(src), output=out.append)
    pipeline.answer.assert_not_called()
