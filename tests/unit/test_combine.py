# tests/unit/test_combine.py
"""双层评估汇总口径：代码层「没判到」不能被当成「判失败」。

回归背景（第二次实验 BC-04）：契约只有语义约束、无任何硬断言，
code_score=0 且 code_coverage=0，judge 判 pass；旧口径 AND 后误判为失败。
"""

from __future__ import annotations

import pytest

from app.evals.combine import combined_score


def test_both_layers_pass() -> None:
    assert combined_score(1.0, 0.6, "pass", 1.0) == 1.0


def test_code_failure_blocks_pass() -> None:
    assert combined_score(0.5, 0.6, "pass", 1.0) == 0.0
    assert combined_score(0.0, 0.6, "pass", 1.0) == 0.0


def test_judge_failure_blocks_pass() -> None:
    assert combined_score(1.0, 0.6, "fail", 0.0) == 0.0
    assert combined_score(1.0, 0.6, "fail", 0.5) == 0.0


def test_no_code_applicable_checks_defers_to_judge() -> None:
    """BC-04：代码层覆盖度为 0 时只按 judge 结论，不参与 AND。"""
    assert combined_score(0.0, 0.0, "pass", 1.0) == 1.0
    assert combined_score(0.0, 0.0, "fail", 0.0) == 0.0


def test_judge_error_or_missing_is_not_a_failure() -> None:
    assert combined_score(1.0, 0.6, "error", 0.0) is None
    assert combined_score(1.0, 0.6, None, 0.0) is None
    assert combined_score(1.0, 0.6, "", 0.0) is None


@pytest.mark.parametrize(
    "bad",
    [
        {"code_score": 1.2},
        {"code_coverage": -0.1},
        {"llm_score": 2.0},
    ],
)
def test_rejects_scores_out_of_range(bad: dict) -> None:
    kw: dict = {
        "code_score": 1.0,
        "code_coverage": 0.6,
        "llm_status": "pass",
        "llm_score": 1.0,
    }
    kw.update(bad)
    with pytest.raises(ValueError):
        combined_score(**kw)
