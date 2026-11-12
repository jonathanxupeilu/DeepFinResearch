# app/evals/llm_judge.py
"""四期第二层评估器：LLM judge 判定语义约束。

第一次代码评估实验（2026-11-06）暴露两件事：``must_mention`` 的裸字符串
匹配制造假阴性；``must_not`` / ``expected_behavior`` 是自然语言、代码层判不了。
本模块把这两类交给 LLM，判**语义**而非文本相似度。

设计红线：
- judge 提示词必须来自 repo 里版本化的 yaml（口径变了分数不可比）；
- judge 调用失败/输出不可解析时返回 ``error`` 状态，**绝不虚报 pass**；
- 纯函数编排 + chat 回调注入，便于单测 mock 且不在评估里引入隐式网络依赖。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]  # PyYAML 未装 stub，运行时类型由 JudgePrompt 校验
from pydantic import BaseModel, Field

from app.evals.code_evaluator import BehaviorContract, EvalObservation

Message = dict[str, str]
ChatFn = Callable[[list[Message], float], str]

_PLACEHOLDER_RE = re.compile(r"<<[A-Z_]+>>")


class JudgePrompt(BaseModel):
    """版本化的 judge 口径；system 与 user_template 均不可为空。"""

    version: int
    system: str
    user_template: str
    name: str = ""
    description: str = ""


class JudgeVerdict(BaseModel):
    """LLM judge 的结构化判定。error 非空时其余字段一律不可信。"""

    behavior_aligned: bool = False
    violated_must_not: list[str] = Field(default_factory=list)
    mentions_satisfied: bool | None = None
    reason: str = ""
    error: str = ""

    @property
    def status(self) -> Literal["pass", "fail", "error"]:
        if self.error:
            return "error"
        aligned = self.behavior_aligned and not self.violated_must_not
        mentions_ok = self.mentions_satisfied in (None, True)
        return "pass" if aligned and mentions_ok else "fail"

    @property
    def score(self) -> float:
        if self.error:
            return 0.0
        checks = [
            self.behavior_aligned,
            not self.violated_must_not,
        ]
        if self.mentions_satisfied is not None:
            checks.append(self.mentions_satisfied)
        return round(sum(1 for c in checks if c) / len(checks), 4)

    @property
    def applicable_checks(self) -> int:
        """judge 实际判定项数（必提语义为空时少一项）。"""
        return 3 if self.mentions_satisfied is not None else 2


def load_judge_prompt(path: Path, version: int | None = None) -> JudgePrompt:
    """加载指定版本；不传则用文件里的当前 version。

    历史版本全文保留在 yaml 的 ``versions`` 下，指定 ``version`` 即可用旧口径
    复跑历史 experiment 做前后对比。兼容早期扁平的单版本文件。
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    chosen = int(version or raw.get("version", 1))
    versions = raw.get("versions") or {}
    if chosen in versions:
        body = versions[chosen]
        return JudgePrompt(
            version=chosen,
            system=str(body["system"]),
            user_template=str(body["user_template"]),
            name=str(raw.get("name", "")),
            description=str(raw.get("description", "")),
        )
    if version is not None:
        raise ValueError(f"judge prompt v{version} 不存在于 {path.name}")
    return JudgePrompt.model_validate(raw)


def _fmt_list(items: list[str]) -> str:
    if not items:
        return "(无)"
    return "\n".join(f"  {i}. {t}" for i, t in enumerate(items, 1))


def _fmt_tool_args(obs: EvalObservation) -> str:
    """工具调用参数：query / time_range 是判「主题词丢失」「时间锚定」的关键证据。"""
    if not obs.tool_arguments:
        return "(无)"
    lines: list[str] = []
    for i, call in enumerate(obs.tool_arguments, 1):
        args = ", ".join(f"{k}={v}" for k, v in call.arguments.items()) or "(无参数)"
        lines.append(f"  {i}. {call.tool}: {args}")
    return "\n".join(lines)


def _fmt_evidence(obs: EvalObservation) -> str:
    """引用切片正文：判「挂无关引用充数」必须看得到切片主题。"""
    if not obs.evidence:
        return "(无)"
    return "\n".join(f"  [{e.marker}] {e.source}: {e.text}" for e in obs.evidence)


def render_judge_messages(
    obs: EvalObservation,
    ct: BehaviorContract,
    question: str,
    p: JudgePrompt,
    code_stats: str | None = None,
) -> list[Message]:
    """一次性占位符替换：答案内容不会被二次扫描，含花括号/占位符文本也安全。

    code_stats 是代码层机械检查的统计摘要，仅作辅助观测；旧版模板无
    <<CODE_STATS>> 占位符，传入也不会改变旧口径的渲染结果。
    """
    replacements = {
        "<<QUESTION>>": question or "(无)",
        "<<EXPECTED_BEHAVIOR>>": ct.expected_behavior or "(无)",
        "<<MUST_MENTION>>": _fmt_list(ct.must_mention),
        "<<MUST_NOT>>": _fmt_list(ct.must_not),
        "<<TOOL_CALLS>>": ", ".join(obs.tool_calls) or "(无)",
        "<<TOOL_ARGUMENTS>>": _fmt_tool_args(obs),
        "<<CITATIONS>>": ", ".join(f"[{c}]" for c in obs.citations) or "(无)",
        "<<EVIDENCE>>": _fmt_evidence(obs),
        "<<CODE_STATS>>": code_stats or "(未提供)",
        "<<ANSWER>>": obs.answer or "(空回答)",
    }
    body = _PLACEHOLDER_RE.sub(
        lambda m: replacements.get(m.group(0), m.group(0)), p.user_template
    )
    return [
        {"role": "system", "content": p.system},
        {"role": "user", "content": body},
    ]


def parse_judge_json(text: str) -> JudgeVerdict:
    """容错解析：模型偶尔带 Markdown 围栏或前后寒暄。"""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("响应中未找到 JSON 对象")
    try:
        raw = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"judge 响应 JSON 解析失败: {e}") from e
    if not isinstance(raw, dict):
        raise TypeError("judge 响应顶层不是对象")
    missing = {"behavior_aligned", "violated_must_not", "reason"} - set(raw)
    if missing:
        raise ValueError(f"judge 响应缺字段: {sorted(missing)}")
    try:
        return JudgeVerdict.model_validate(raw)
    except ValueError as e:
        raise ValueError(f"judge 响应字段不合法: {e}") from e


def judge_contract(
    obs: EvalObservation,
    ct: BehaviorContract,
    question: str,
    chat: ChatFn,
    p: JudgePrompt,
    temperature: float = 0.0,
    code_stats: str | None = None,
) -> JudgeVerdict:
    """调用 LLM 判语义；任何失败都降级为 error，不抛给 LangSmith 吞掉。"""
    messages = render_judge_messages(obs, ct, question, p, code_stats=code_stats)
    try:
        raw = chat(messages, temperature)
        verdict = parse_judge_json(raw)
    except (ValueError, TypeError) as e:
        return JudgeVerdict(error=f"judge 响应解析失败: {e}")
    except Exception as e:  # noqa: BLE001 — judge 故障不能让整场 experiment 崩
        return JudgeVerdict(error=f"judge 调用失败: {type(e).__name__}: {e}")
    # 契约里没有必提语义时，模型多给的判定一律丢弃，避免虚增反馈项
    if not ct.must_mention and verdict.mentions_satisfied is not None:
        verdict = verdict.model_copy(update={"mentions_satisfied": None})
    return verdict


def judge_to_feedback(v: JudgeVerdict) -> list[dict]:
    """JudgeVerdict → LangSmith evaluator 返回格式（多个 feedback key）。"""
    err_note = f"judge 不可用: {v.error}" if v.error else ""
    violated = " | ".join(v.violated_must_not) or "无"
    feedback: list[dict] = [
        {
            "key": "llm_behavior_aligned",
            "score": 1.0 if (not v.error and v.behavior_aligned) else 0.0,
            "comment": err_note or f"期望行为一致性；{v.reason}",
        },
        {
            "key": "llm_must_not",
            "score": 1.0 if (not v.error and not v.violated_must_not) else 0.0,
            "comment": err_note or f"违反的禁止项: {violated}；{v.reason}",
        },
    ]
    if v.mentions_satisfied is not None:
        feedback.append(
            {
                "key": "llm_must_mention",
                "score": 1.0 if (not v.error and v.mentions_satisfied) else 0.0,
                "comment": err_note or f"必提语义满足情况；{v.reason}",
            }
        )
    feedback.append(
        {
            "key": "llm_judge_score",
            "score": v.score,
            "comment": err_note or f"语义判定通过率 {v.score}；{v.reason}",
        }
    )
    feedback.append(
        {
            "key": "llm_judge_status",
            "score": 1.0 if v.status != "error" else 0.0,
            "comment": f"status={v.status}"
            + (f" | {v.error}" if v.error else f" | {v.reason}"),
        }
    )
    return feedback
