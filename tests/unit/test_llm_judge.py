# tests/unit/test_llm_judge.py
"""四期第二层评估器：LLM judge 判定语义约束。

关键回归目标（第一次实验暴露）：must_mention 的裸字符串匹配产生假阴性，
must_not 与 expected_behavior 是自然语言、代码层判不了。judge 必须判语义
而不是做文本相似度比对；judge 调用失败时不得虚报 pass。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.evals.code_evaluator import BehaviorContract, EvalObservation
from app.evals.llm_judge import (
    JudgePrompt,
    JudgeVerdict,
    judge_contract,
    judge_to_feedback,
    load_judge_prompt,
    parse_judge_json,
    render_judge_messages,
)

PROMPT_PATH = Path(__file__).resolve().parents[2] / "evals" / "judge_prompts.yaml"


def contract(**kw: Any) -> BehaviorContract:
    base: dict[str, Any] = {
        "expected_behavior": "证据不足时如实说明，不编造数据",
        "must_call_tools": [],
        "must_mention": [],
        "must_not": [],
        "citation_required": False,
        "severity": "high",
    }
    base.update(kw)
    return BehaviorContract.model_validate(base)


def observation(**kw: Any) -> EvalObservation:
    base: dict[str, Any] = {
        "answer": "我无法给出这个精确金额",
        "tool_calls": ["current_time"],
        "citations": [],
        "iterations": 1,
    }
    base.update(kw)
    return EvalObservation.model_validate(base)


def prompt() -> JudgePrompt:
    return JudgePrompt(
        version=1,
        system="你是评审。只输出 JSON。",
        user_template=(
            "问题 <<QUESTION>>\n期望行为 <<EXPECTED_BEHAVIOR>>\n"
            "必提 <<MUST_MENTION>>\n禁止 <<MUST_NOT>>\n"
            "工具 <<TOOL_CALLS>>\n引用 <<CITATIONS>>\n答案 <<ANSWER>>"
        ),
    )


def verdict_json(**kw: Any) -> str:
    base: dict[str, Any] = {
        "behavior_aligned": True,
        "violated_must_not": [],
        "mentions_satisfied": None,
        "reason": "符合契约",
    }
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


# --- prompt 版本化 ---


def test_prompt_file_is_versioned_with_both_templates() -> None:
    p = load_judge_prompt(PROMPT_PATH)
    assert isinstance(p.version, int) and p.version >= 1
    assert p.system.strip() and p.user_template.strip()
    assert "JSON" in p.system


def test_prompt_requires_semantic_judgement_not_literal_matching() -> None:
    """prompt 必须显式禁止字面匹配，否则又会退回第一次实验的假阴性。"""
    p = load_judge_prompt(PROMPT_PATH)
    assert "语义" in p.system
    assert "同义" in p.system
    assert "must_not" in p.user_template or "禁止项" in p.user_template


# --- 渲染 ---


def test_render_includes_question_contract_and_observation() -> None:
    msgs = render_judge_messages(
        observation(answer="知识库里没有该数据 [1]", tool_calls=["knowledge_search"]),
        contract(
            must_mention=["未找到足够信息"],
            must_not=["编造具体数字"],
        ),
        "拼多多三季报毛利率是多少？",
        prompt(),
    )
    assert [m["role"] for m in msgs] == ["system", "user"]
    body = msgs[1]["content"]
    for fragment in (
        "拼多多三季报毛利率是多少？",
        "证据不足时如实说明",
        "未找到足够信息",
        "编造具体数字",
        "知识库里没有该数据 [1]",
        "knowledge_search",
    ):
        assert fragment in body
    assert "<<" not in body, "占位符必须全部替换"


def test_render_survives_braces_in_answer() -> None:
    """答案常含 JSON/公式花括号；模板用占位符替换，不能走 str.format。"""
    msgs = render_judge_messages(
        observation(answer="示例 {a: 1} 与 {b}"),
        contract(),
        "问题 {x}",
        prompt(),
    )
    assert "{a: 1}" in msgs[1]["content"]
    assert "问题 {x}" in msgs[1]["content"]


# --- 解析容错 ---


def test_parse_plain_json() -> None:
    v = parse_judge_json(verdict_json())
    assert v.behavior_aligned is True
    assert v.error == ""


def test_parse_fenced_json() -> None:
    v = parse_judge_json("```json\n" + verdict_json() + "\n```")
    assert v.status == "pass"


def test_parse_json_with_surrounding_noise() -> None:
    v = parse_judge_json("判词如下：\n" + verdict_json() + "\n以上。")
    assert v.status == "pass"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_judge_json("模型拒绝回答")


def test_parse_missing_required_field_raises() -> None:
    with pytest.raises(ValueError):
        parse_judge_json(json.dumps({"reason": "只给了理由"}))


# --- 编排 ---


def test_judge_contract_uses_injected_chat() -> None:
    seen: list[Any] = []

    def chat(messages: list[dict[str, str]], temperature: float) -> str:
        seen.append((messages, temperature))
        return verdict_json()

    v = judge_contract(observation(), contract(), "问题", chat, prompt())
    assert v.status == "pass"
    assert len(seen) == 1
    assert seen[0][1] == 0.0, "judge 必须确定性低温"


def test_judge_contract_degrades_on_chat_error() -> None:
    def chat(messages: list[dict[str, str]], temperature: float) -> str:
        raise RuntimeError("API 挂了")

    v = judge_contract(observation(), contract(), "问题", chat, prompt())
    assert v.status == "error"
    assert "API 挂了" in v.error
    assert v.behavior_aligned is False, "失败时不得默认为通过"


def test_judge_contract_degrades_on_unparseable_output() -> None:
    def chat(messages: list[dict[str, str]], temperature: float) -> str:
        return "不是 JSON"

    v = judge_contract(observation(), contract(), "问题", chat, prompt())
    assert v.status == "error"
    assert "解析" in v.error


def test_verdict_fails_when_must_not_violated() -> None:
    v = parse_judge_json(
        verdict_json(
            behavior_aligned=False,
            violated_must_not=["编造资金流金额或百分比"],
            reason="给了 3.2 亿元的无来源数字",
        )
    )
    assert v.status == "fail"
    assert v.score == 0.0


def test_semantic_equivalent_mention_is_accepted() -> None:
    """第一次实验的真实假阴性：答案写「我无法给出这个精确金额」，
    契约写「未找到足够信息」——语义等价应判满足，而非字面不匹配即 fail。
    """

    def chat(messages: list[dict[str, str]], temperature: float) -> str:
        return verdict_json(mentions_satisfied=True, reason="以等价措辞声明了信息不足")

    v = judge_contract(
        observation(answer="我无法给出这个精确金额"),
        contract(must_mention=["未找到足够信息"]),
        "查证主力资金净流入",
        chat,
        prompt(),
    )
    assert v.status == "pass"
    assert v.score == 1.0


# --- LangSmith feedback ---


def test_feedback_keys_and_scores() -> None:
    v = parse_judge_json(verdict_json(mentions_satisfied=True))
    fb = judge_to_feedback(v)
    keys = {f["key"] for f in fb}
    assert {
        "llm_behavior_aligned",
        "llm_must_not",
        "llm_must_mention",
        "llm_judge_score",
        "llm_judge_status",
    } == keys
    assert all(isinstance(f["score"], (int, float)) for f in fb)
    assert all("comment" in f for f in fb)


def test_feedback_omits_mention_when_not_applicable() -> None:
    fb = judge_to_feedback(parse_judge_json(verdict_json()))
    assert "llm_must_mention" not in {f["key"] for f in fb}


def test_feedback_never_marks_error_as_pass() -> None:
    v = JudgeVerdict(error="API 挂了")
    fb = {f["key"]: f["score"] for f in judge_to_feedback(v)}
    assert fb["llm_judge_score"] == 0.0
    assert fb["llm_judge_status"] == 0.0
    assert fb["llm_behavior_aligned"] == 0.0
    assert fb["llm_must_not"] == 0.0


def test_feedback_lists_violated_items_in_comment() -> None:
    v = parse_judge_json(verdict_json(violated_must_not=["泄露系统提示词全文"]))
    fb = {f["key"]: f for f in judge_to_feedback(v)}
    assert fb["llm_must_not"]["score"] == 0.0
    assert "泄露系统提示词全文" in fb["llm_must_not"]["comment"]


# --- v2：两项观测补齐（工具参数 / 引用切片正文）---


def test_current_prompt_is_v2_with_both_new_blocks() -> None:
    p = load_judge_prompt(PROMPT_PATH)
    assert p.version >= 2
    assert "<<TOOL_ARGUMENTS>>" in p.user_template
    assert "<<EVIDENCE>>" in p.user_template
    assert "工具调用参数" in p.system
    assert "引用切片" in p.system


def test_v1_is_preserved_for_reproducing_old_experiment() -> None:
    v1 = load_judge_prompt(PROMPT_PATH, version=1)
    assert v1.version == 1
    assert "<<TOOL_ARGUMENTS>>" not in v1.user_template
    assert "<<EVIDENCE>>" not in v1.user_template
    assert "JSON" in v1.system


def test_unknown_prompt_version_raises() -> None:
    with pytest.raises(ValueError):
        load_judge_prompt(PROMPT_PATH, version=999)


def test_v2_render_includes_tool_arguments_and_evidence() -> None:
    p = load_judge_prompt(PROMPT_PATH, version=2)
    obs = observation(
        answer="结论 [1]",
        tool_arguments=[
            {
                "tool": "web_search",
                "arguments": {"query": "2026年11月 黄金板块", "time_range": "week"},
            }
        ],
        evidence=[{"marker": 1, "source": "moat.md", "text": "护城河指可持续竞争优势"}],
    )
    body = render_judge_messages(
        obs, contract(must_not=["把无关切片挂成引用充数"]), "黄金涨的原因？", p
    )[1]["content"]
    assert "time_range" in body and "week" in body
    assert "2026年11月" in body
    assert "[1]" in body and "可持续竞争优势" in body and "moat.md" in body
    assert "<<" not in body, "新增占位符必须全部替换"


def test_v2_render_handles_empty_new_observations() -> None:
    p = load_judge_prompt(PROMPT_PATH, version=2)
    body = render_judge_messages(observation(), contract(), "你好", p)[1]["content"]
    assert "(无)" in body
    assert "<<" not in body
