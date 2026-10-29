# tests/unit/test_cli.py
from unittest.mock import MagicMock

from pydantic import BaseModel, ValidationError

from app import cli
from app.cli import format_answer, run
from app.models import Citation, RagAnswer


def _validation_error() -> ValidationError:
    """构造一个真实的 pydantic ValidationError（模拟缺密钥场景）。"""

    class _Model(BaseModel):
        required_key: str

    try:
        _Model()  # type: ignore[call-arg]
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


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


def test_run_survives_answer_exception():
    # 第一个问题抛异常（模拟 API 挂掉），第二个问题正常回答——会话不应死亡
    pipeline = MagicMock()
    pipeline.answer.side_effect = [
        Exception("api down"),
        RagAnswer(answer="恢复后的回答", citations=[]),
    ]
    inputs = iter(["第一个问题", "第二个问题", "/exit"])
    out: list[str] = []
    run(pipeline, input_fn=lambda _: next(inputs), output=out.append)
    assert pipeline.answer.call_count == 2
    assert any("出错" in line and "api down" in line for line in out)
    assert any("恢复后的回答" in line for line in out)


def test_run_ignores_blank_and_eof():
    pipeline = _mock_pipeline("x")
    inputs = iter(["", "  ", "有效问题", "/exit"])
    out: list[str] = []
    run(pipeline, input_fn=lambda _: next(inputs), output=out.append)
    # 空白输入被忽略，只有"有效问题"触发了回答
    pipeline.answer.assert_called_once_with("有效问题")
    assert any("x" in line for line in out)


def test_run_exit_aliases():
    pipeline = _mock_pipeline("x")
    for alias in ("/exit", "/quit", "exit", "q"):
        inputs = iter([alias])
        out: list[str] = []
        run(pipeline, input_fn=lambda _, src=inputs: next(src), output=out.append)
    pipeline.answer.assert_not_called()


def test_main_friendly_error_on_missing_api_key(monkeypatch, capsys):
    def _boom():
        raise _validation_error()

    monkeypatch.setattr(cli, "build_pipeline", _boom)
    rc = cli.main()
    assert rc == 1
    captured = capsys.readouterr()
    assert "缺少必需的 API Key" in captured.out
    assert "DEEPSEEK_API_KEY" in captured.out
