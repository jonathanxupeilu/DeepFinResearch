# tests/unit/test_code_evaluator.py
"""四期代码评估器：行为契约的可机械断言子集 + 覆盖度诚实上报。

契约里的 must_not 是自然语言，代码层判不了，一律标 skip 交 LLM/人工；
评估器不得把 skip 当成 pass，否则第一张分数表会虚高。
"""

from __future__ import annotations

import pytest

from app.evals.code_evaluator import (
    BehaviorContract,
    EvalObservation,
    check_contract,
    observation_from_answer,
    to_feedback,
)
from app.models import Citation, RagAnswer, TraceStep


def contract(**kw) -> BehaviorContract:
    base = {
        "expected_behavior": "按契约作答",
        "must_call_tools": [],
        "must_mention": [],
        "must_not": [],
        "citation_required": False,
        "severity": "high",
    }
    base.update(kw)
    return BehaviorContract.model_validate(base)


def observation(**kw) -> EvalObservation:
    base = {"answer": "一段回答", "tool_calls": [], "citations": [], "iterations": 1}
    base.update(kw)
    return EvalObservation.model_validate(base)


def by_key(verdict, key: str):
    return next(c for c in verdict.checks if c.key == key)


def test_all_required_tools_present_passes() -> None:
    v = check_contract(
        observation(tool_calls=["current_time", "knowledge_search", "web_search"]),
        contract(must_call_tools=["current_time", "web_search"]),
    )
    assert by_key(v, "must_call_tools").status == "pass"


def test_missing_required_tool_fails_with_name() -> None:
    v = check_contract(
        observation(tool_calls=["knowledge_search"]),
        contract(must_call_tools=["current_time"]),
    )
    chk = by_key(v, "must_call_tools")
    assert chk.status == "fail"
    assert "current_time" in chk.detail


def test_empty_must_call_tools_is_skipped_not_passed() -> None:
    """空数组语义歧义（不要求 or 禁止），不能当成 pass。"""
    v = check_contract(observation(tool_calls=[]), contract(must_call_tools=[]))
    chk = by_key(v, "must_call_tools")
    assert chk.status == "skip"
    assert "歧义" in chk.detail


def test_must_mention_checks_each_keyword() -> None:
    """可选的字面模式（B 方案默认关闭，仅保留作调试/回归用）。"""
    v = check_contract(
        observation(answer="消费板块需要验证内需传导"),
        contract(must_mention=["消费", "风险"]),
        literal_mentions=True,
    )
    chk = by_key(v, "must_mention")
    assert chk.status == "fail"
    assert "风险" in chk.detail
    v2 = check_contract(
        observation(answer="消费板块有风险"),
        contract(must_mention=["消费", "风险"]),
        literal_mentions=True,
    )
    assert by_key(v2, "must_mention").status == "pass"


def test_must_mention_delegated_to_llm_by_default() -> None:
    """B 方案：字面匹配产生假阴性，默认委派给 LLM judge 判语义等价。"""
    v = check_contract(
        observation(answer="我无法给出这个精确金额"),
        contract(must_mention=["未找到足够信息"]),
    )
    chk = by_key(v, "must_mention")
    assert chk.status == "skip"
    assert "LLM" in chk.detail


def test_citation_required_true_needs_markers_and_sources() -> None:
    v = check_contract(
        observation(answer="没有标注引用", citations=[1]),
        contract(citation_required=True),
    )
    assert by_key(v, "citation_required").status == "fail"
    v2 = check_contract(
        observation(answer="护城河理论 [1]", citations=[1]),
        contract(citation_required=True),
    )
    assert by_key(v2, "citation_required").status == "pass"


def test_citation_required_false_is_skipped() -> None:
    """不要求引用 != 禁止引用，不能反向判 fail。"""
    v = check_contract(observation(answer="无引用"), contract(citation_required=False))
    assert by_key(v, "citation_required").status == "skip"


def test_out_of_range_marker_fails() -> None:
    """真实基线翻车：答案出现 [1][6] 但 citations 只有 4 个。"""
    v = check_contract(
        observation(answer="护城河指可持续竞争优势 [1][6]", citations=[1, 2, 3, 4]),
        contract(citation_required=True),
    )
    chk = by_key(v, "citations_in_range")
    assert chk.status == "fail"
    assert "6" in chk.detail


def test_in_range_marker_passes() -> None:
    v = check_contract(
        observation(answer="护城河 [1][3]", citations=[1, 2, 3]),
        contract(citation_required=True),
    )
    assert by_key(v, "citations_in_range").status == "pass"


def test_must_not_is_always_skipped_and_reports_count() -> None:
    v = check_contract(
        observation(),
        contract(must_not=["编造资金流金额", "把无来源数据当结论"]),
    )
    chk = by_key(v, "must_not")
    assert chk.status == "skip"
    assert "2" in chk.detail
    assert "LLM" in chk.detail or "人工" in chk.detail


def test_score_excludes_skipped_checks() -> None:
    v = check_contract(
        observation(tool_calls=["knowledge_search"]),
        contract(must_call_tools=["knowledge_search"], must_not=["编造数字"]),
    )
    assert v.score == 1.0
    assert 0 < v.coverage < 1
    assert len(v.skipped) >= 1


def test_score_zero_when_nothing_applicable() -> None:
    v = check_contract(observation(), contract())
    assert v.score == 0.0
    assert v.coverage == 0.0, "无可判项时覆盖度必须为 0，防止虚高"


def test_to_feedback_omits_skips_but_reports_coverage() -> None:
    v = check_contract(
        observation(tool_calls=["knowledge_search"]),
        contract(must_call_tools=["knowledge_search"], must_not=["编造数字"]),
    )
    fb = to_feedback(v)
    keys = {f["key"] for f in fb}
    assert "code_contract_score" in keys and "code_coverage" in keys
    assert all("skip" not in k for k in keys)
    assert all("score" in f and isinstance(f["score"], (int, float)) for f in fb)


def test_observation_from_rag_answer_extracts_tools_and_citations() -> None:
    ans = RagAnswer(
        answer="护城河 [1]",
        citations=[Citation(marker=1, source="a.md", text="切片")],
        trace=[
            TraceStep(step=1, tool="knowledge_search", arguments={"query": "护城河"}),
            TraceStep(step=2, tool="current_time", arguments={}),
        ],
    )
    obs = observation_from_answer(ans)
    assert obs.tool_calls == ["knowledge_search", "current_time"]
    assert obs.citations == [1]
    assert obs.iterations == 2
    assert obs.answer == "护城河 [1]"


@pytest.mark.parametrize("bad", [{"tool_calls": "not-a-list"}, {"answer": 123}])
def test_models_reject_wrong_types(bad: dict) -> None:
    with pytest.raises(ValueError):
        observation(**bad)


# --- judge 观测补齐：工具参数 + 引用切片正文 ---


def test_observation_extracts_tool_arguments() -> None:
    ans = RagAnswer(
        answer="黄金 [1]",
        trace=[
            TraceStep(
                step=1,
                tool="web_search",
                arguments={"query": "2026年11月 黄金板块 涨幅", "time_range": "week"},
            )
        ],
    )
    obs = observation_from_answer(ans)
    assert len(obs.tool_arguments) == 1
    assert obs.tool_arguments[0].tool == "web_search"
    assert obs.tool_arguments[0].arguments["time_range"] == "week"
    assert "2026年11月" in obs.tool_arguments[0].arguments["query"]


def test_observation_extracts_evidence_text() -> None:
    ans = RagAnswer(
        answer="护城河 [1]",
        citations=[
            Citation(marker=1, source="moat.md", text="护城河指企业的可持续竞争优势")
        ],
    )
    obs = observation_from_answer(ans)
    assert obs.evidence[0].marker == 1
    assert obs.evidence[0].source == "moat.md"
    assert "可持续竞争优势" in obs.evidence[0].text


def test_observation_prioritizes_cited_evidence() -> None:
    """答案标了 [20] 时也要把该切片喂给 judge，否则判不了引用相关性。"""
    cites = [
        Citation(marker=i, source=f"s{i}.md", text=f"切片{i}") for i in range(1, 25)
    ]
    obs = observation_from_answer(RagAnswer(answer="结论 [20]", citations=cites))
    assert obs.evidence[0].marker == 20


def test_observation_clips_long_arguments_and_evidence() -> None:
    from app.evals.code_evaluator import (
        MAX_ARG_VALUE_CHARS,
        MAX_EVIDENCE_CHARS,
        MAX_EVIDENCE_ITEMS,
    )

    ans = RagAnswer(
        answer="结论 [1]",
        citations=[
            Citation(marker=i + 1, source="s.md", text="内容" * 500) for i in range(20)
        ],
        trace=[TraceStep(step=1, tool="web_search", arguments={"query": "黄" * 1000})],
    )
    obs = observation_from_answer(ans)
    assert len(obs.evidence) <= MAX_EVIDENCE_ITEMS
    assert all(len(e.text) <= MAX_EVIDENCE_CHARS + 1 for e in obs.evidence)
    assert len(obs.tool_arguments[0].arguments["query"]) <= MAX_ARG_VALUE_CHARS + 1


def test_observation_roundtrips_through_model_validate() -> None:
    """LangSmith outputs 是 model_dump() 后的裸 dict，必须能还原成模型。"""
    ans = RagAnswer(
        answer="护城河 [1]",
        citations=[Citation(marker=1, source="a.md", text="切片正文")],
        trace=[
            TraceStep(step=1, tool="knowledge_search", arguments={"query": "护城河"})
        ],
    )
    obs = observation_from_answer(ans)
    restored = EvalObservation.model_validate(obs.model_dump())
    assert restored.tool_arguments == obs.tool_arguments
    assert restored.evidence == obs.evidence
