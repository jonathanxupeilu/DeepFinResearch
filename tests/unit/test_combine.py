# tests/unit/test_combine.py
"""汇总分只按 judge；代码层是可观测、可归因的统计信号，不参与判分。

历史背景（D021）：旧口径用 AND 合并，code_coverage=0 时「没判到」被当成
「判失败」（BC-04 假阴性），曾修补为 cov=0 时只按 judge。D027 进一步定案：
代码层整体定位为辅助统计手段，汇总分一律只按 judge。
"""

from __future__ import annotations

import pytest

from app.evals.combine import combined_score


def test_judge_pass_is_pass() -> None:
    assert combined_score(1.0, 0.6, "pass", 1.0) == 1.0


def test_code_stats_never_block_pass() -> None:
    """代码层分值与覆盖度只是统计信号，不改变 judge 结论。"""
    assert combined_score(0.5, 0.6, "pass", 1.0) == 1.0
    assert combined_score(0.0, 0.6, "pass", 1.0) == 1.0
    assert combined_score(0.0, 0.0, "pass", 1.0) == 1.0


def test_no_code_applicable_checks_still_defers_to_judge() -> None:
    """D021 / BC-04：覆盖度为 0 时结论仍只由 judge 决定，不算「没判到=失败」。"""
    assert combined_score(0.0, 0.0, "pass", 1.0) == 1.0
    assert combined_score(0.0, 0.0, "fail", 0.0) == 0.0


def test_judge_failure_is_failure() -> None:
    assert combined_score(1.0, 0.6, "fail", 0.0) == 0.0
    assert combined_score(1.0, 0.6, "fail", 0.5) == 0.0
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
