# app/evals/code_evaluator.py
"""四期第一层评估器：只判行为契约里可机械断言的字段。

``must_not`` / ``expected_behavior`` 是自然语言，``must_mention`` 需要语义等价
判断（第一次实验证明裸字符串匹配全是假阴性），这三类一律标 ``skip``，交第二层
``app.evals.llm_judge`` / 第三层人工审批。代码层只保留：
must_call_tools、citation_required、citations_in_range。

``EvalObservation`` 同时是 judge 的观测输入：除答案与工具名外，还带工具调用参数
（query / time_range）与引用切片正文，供 judge 判「检索主题词是否保留」「是否挂
无关引用充数」。两类观测均有截断上限，避免一次评估塞爆上下文。

设计红线：**skip 绝不能算作 pass**，否则分数表会虚高。
``literal_mentions=True`` 仅供调试/回归旧的裸匹配行为，默认关闭。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import RagAnswer

_CITE_RE = re.compile(r"\[(\d+)\]")

# judge 观测上限：够判语义即可，不把整篇知识库塞进 prompt
MAX_ARG_VALUE_CHARS = 200
MAX_EVIDENCE_ITEMS = 12
MAX_EVIDENCE_CHARS = 240

CheckStatus = Literal["pass", "fail", "skip"]


class ToolCallObs(BaseModel):
    """一次工具调用的参数（值统一转字符串并截断）。"""

    tool: str
    arguments: dict[str, str] = Field(default_factory=dict)


class EvidenceObs(BaseModel):
    """一条引用对应的切片正文（截断）。"""

    marker: int
    source: str = ""
    text: str = ""


class EvalObservation(BaseModel):
    """target 产出的、评估器与 judge 共用的可观测事实。"""

    answer: str
    tool_calls: list[str] = Field(default_factory=list)
    citations: list[int] = Field(default_factory=list)
    iterations: int = 0
    tool_arguments: list[ToolCallObs] = Field(default_factory=list)
    evidence: list[EvidenceObs] = Field(default_factory=list)


class BehaviorContract(BaseModel):
    """LangSmith example.outputs：期望行为契约（不是标准答案）。"""

    expected_behavior: str = ""
    must_call_tools: list[str] = Field(default_factory=list)
    must_mention: list[str] = Field(default_factory=list)
    must_not: list[str] = Field(default_factory=list)
    citation_required: bool = False
    severity: str = "medium"


class CheckResult(BaseModel):
    key: str
    status: CheckStatus
    detail: str = ""


class EvalVerdict(BaseModel):
    checks: list[CheckResult]

    @property
    def applicable(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status != "skip"]

    @property
    def skipped(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == "skip"]

    @property
    def score(self) -> float:
        """只按可判项算通过率；无可判项时返回 0（配合 coverage=0 表达「没判到」）。"""
        applicable = self.applicable
        if not applicable:
            return 0.0
        passed = sum(1 for c in applicable if c.status == "pass")
        return round(passed / len(applicable), 4)

    @property
    def coverage(self) -> float:
        if not self.checks:
            return 0.0
        return round(len(self.applicable) / len(self.checks), 4)


def _check_tools(obs: EvalObservation, ct: BehaviorContract) -> CheckResult:
    if not ct.must_call_tools:
        return CheckResult(
            key="must_call_tools",
            status="skip",
            detail="空数组语义歧义（不要求 or 禁止调用），需显式 must_not_call_tools 才可判",
        )
    missing = [t for t in ct.must_call_tools if t not in obs.tool_calls]
    if missing:
        return CheckResult(
            key="must_call_tools",
            status="fail",
            detail=f"未调用: {', '.join(missing)}（实际: {', '.join(obs.tool_calls) or '无'}）",
        )
    return CheckResult(
        key="must_call_tools",
        status="pass",
        detail=f"已调用: {', '.join(ct.must_call_tools)}",
    )


def _check_mentions(obs: EvalObservation, ct: BehaviorContract) -> CheckResult:
    """旧的字面匹配实现：保留作可选调试模式，默认不进 check_contract。"""
    if not ct.must_mention:
        return CheckResult(key="must_mention", status="skip", detail="契约未要求必提词")
    missing = [w for w in ct.must_mention if w not in obs.answer]
    if missing:
        return CheckResult(
            key="must_mention",
            status="fail",
            detail=f"答案未提及: {', '.join(missing)}",
        )
    return CheckResult(
        key="must_mention",
        status="pass",
        detail=f"已提及: {', '.join(ct.must_mention)}",
    )


def _check_mention_delegated(ct: BehaviorContract) -> CheckResult:
    if not ct.must_mention:
        return CheckResult(
            key="must_mention", status="skip", detail="契约未要求必提语义"
        )
    return CheckResult(
        key="must_mention",
        status="skip",
        detail=f"{len(ct.must_mention)} 项必提语义需同义判断，交 LLM judge",
    )


def _check_citation_required(obs: EvalObservation, ct: BehaviorContract) -> CheckResult:
    if not ct.citation_required:
        return CheckResult(
            key="citation_required",
            status="skip",
            detail="不要求引用 != 禁止引用，不做反向断言",
        )
    has_marker = bool(_CITE_RE.search(obs.answer))
    if not has_marker:
        return CheckResult(
            key="citation_required", status="fail", detail="答案无 [n] 标注"
        )
    if not obs.citations:
        return CheckResult(
            key="citation_required", status="fail", detail="有 [n] 标注但无引用来源"
        )
    return CheckResult(key="citation_required", status="pass", detail="标注与来源齐备")


def _check_citations_in_range(obs: EvalObservation) -> CheckResult:
    """通用回归：答案里越界的 [n] 编号（基线里真实出现过 [1][6] 而 cites=4）。"""
    markers = [int(m) for m in _CITE_RE.findall(obs.answer)]
    if not markers:
        return CheckResult(
            key="citations_in_range", status="skip", detail="答案无 [n] 标注"
        )
    upper = max(obs.citations) if obs.citations else 0
    bad = sorted({m for m in markers if m < 1 or m > upper})
    if bad:
        return CheckResult(
            key="citations_in_range",
            status="fail",
            detail=f"越界编号: {bad}（有效上限 {upper}）",
        )
    return CheckResult(
        key="citations_in_range", status="pass", detail="编号均在来源范围内"
    )


def _check_must_not(ct: BehaviorContract) -> CheckResult:
    if not ct.must_not:
        return CheckResult(key="must_not", status="skip", detail="契约无禁止项")
    return CheckResult(
        key="must_not",
        status="skip",
        detail=f"{len(ct.must_not)} 条语义禁止项交 LLM judge / 人工审批，代码层不判",
    )


def check_contract(
    obs: EvalObservation, ct: BehaviorContract, *, literal_mentions: bool = False
) -> EvalVerdict:
    """纯函数：一次问答的可观测事实 × 行为契约 → 分项判定。

    ``literal_mentions=True`` 会启用旧的裸字符串匹配（仅调试/回归用）；默认
    委派语义判断给 LLM judge，避免第一次实验里的同义表达假阴性。
    """
    mention_check = (
        _check_mentions(obs, ct) if literal_mentions else _check_mention_delegated(ct)
    )
    return EvalVerdict(
        checks=[
            _check_tools(obs, ct),
            mention_check,
            _check_citation_required(obs, ct),
            _check_citations_in_range(obs),
            _check_must_not(ct),
        ]
    )


def _clip(text: Any, limit: int) -> str:
    """压平空白再截断；截断处以 … 标记，避免 judge 误以为看到全文。"""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _clip_arguments(arguments: dict[str, Any]) -> dict[str, str]:
    return {str(k): _clip(v, MAX_ARG_VALUE_CHARS) for k, v in arguments.items()}


def observation_from_answer(ans: RagAnswer) -> EvalObservation:
    """RagAnswer → 评估器/judge 观测；补齐工具参数与引用切片正文。

    引用切片优先保留答案实际标注的编号（否则答案写 [20] 时 judge 只看得到前
    12 条，无法判「挂无关引用」），再按上限截断数量与单条长度。
    """
    cited = {int(m) for m in _CITE_RE.findall(ans.answer)}
    ordered = [c for c in ans.citations if c.marker in cited] + [
        c for c in ans.citations if c.marker not in cited
    ]
    return EvalObservation(
        answer=ans.answer,
        tool_calls=[s.tool for s in ans.trace],
        citations=[c.marker for c in ans.citations],
        iterations=len({s.step for s in ans.trace}),
        tool_arguments=[
            ToolCallObs(tool=s.tool, arguments=_clip_arguments(s.arguments))
            for s in ans.trace
        ],
        evidence=[
            EvidenceObs(
                marker=c.marker,
                source=c.source,
                text=_clip(c.text, MAX_EVIDENCE_CHARS),
            )
            for c in ordered[:MAX_EVIDENCE_ITEMS]
        ],
    )


def to_feedback(verdict: EvalVerdict) -> list[dict]:
    """EvalVerdict → LangSmith evaluator 返回格式（多个 feedback key）。

    skip 项不单独生成 feedback，但在 code_coverage 的 comment 里逐条列明，
    保证网页端能看出「哪些维度根本没判」。
    """
    feedback: list[dict] = []
    for chk in verdict.applicable:
        feedback.append(
            {
                "key": f"code_{chk.key}",
                "score": 1.0 if chk.status == "pass" else 0.0,
                "comment": chk.detail,
            }
        )
    feedback.append(
        {
            "key": "code_contract_score",
            "score": verdict.score,
            "comment": f"硬断言通过率 {verdict.score}；分值为 0 且覆盖度为 0 时代表无可判项，非真实失败",
        }
    )
    feedback.append(
        {
            "key": "code_coverage",
            "score": verdict.coverage,
            "comment": "跳过: "
            + (" | ".join(f"{c.key}: {c.detail}" for c in verdict.skipped) or "无"),
        }
    )
    return feedback
