# app/evals/combine.py
"""双层评估汇总口径（纯函数，便于单测与历史明细复算）。

关键语义：**代码层「没判到」不等于「判失败」**。
当 code_coverage=0（契约全是语义约束、无任何硬断言）时，combined 只按
judge 结论；judge 缺判/报错时返回 None，既不记通过也不记失败。
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
    judge_ok = llm_score == 1.0
    if code_coverage == 0.0:
        return 1.0 if judge_ok else 0.0
    return 1.0 if (code_score == 1.0 and judge_ok) else 0.0
