# app/evals/combine.py
"""汇总分口径（纯函数，便于单测与历史明细复算）。

关键语义：**代码层是辅助判断的统计手段，不是 pass/fail 硬约束**。
汇总分只按 judge 结论；code_score / code_coverage 保留在签名与明细中，
供可观测、可归因的统计输出，不参与判分。判分以行为契约 / judge 为准。

judge 缺判或报错时返回 None：既不记通过也不记失败。
"""

from __future__ import annotations


def combined_score(
    code_score: float,
    code_coverage: float,
    llm_status: str | None,
    llm_score: float,
) -> float | None:
    for name, value in (
        ("code_score", code_score),
        ("code_coverage", code_coverage),
        ("llm_score", llm_score),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} 超出 [0,1]: {value}")
    if llm_status in (None, "", "error"):
        return None
    return 1.0 if llm_score == 1.0 else 0.0
