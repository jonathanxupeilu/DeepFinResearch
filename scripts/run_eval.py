# scripts/run_eval.py
"""四期评估实验：LLM judge 行为契约判分 + 代码层统计信号（混装）。

用法：
  .venv/Scripts/python.exe scripts/run_eval.py --dry-run        # 不调 LLM、不写云端
  .venv/Scripts/python.exe scripts/run_eval.py                 # common_questions 全 10 条
  .venv/Scripts/python.exe scripts/run_eval.py --only BC-09,BC-10
  .venv/Scripts/python.exe scripts/run_eval.py --evaluators code   # 只跑代码层
  .venv/Scripts/python.exe scripts/run_eval.py --repetitions 3
  .venv/Scripts/python.exe scripts/run_eval.py --judge-version 1    # 用旧口径复跑对比
  .venv/Scripts/python.exe scripts/run_eval.py --from-results evals/results/eval_*.jsonl

设计约束（用户 2026-11-06 定）：每题跑一次、只跑 common_questions。
B 方案：must_not / expected_behavior / 语义 must_mention 交 LLM judge；
代码层只产出工具序列、引用要求、编号越界等统计信号，不参与判分（D027）。
judge 走不带追踪包装的原生客户端，
避免 judge 自身的调用污染实验 trace。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.evals.code_evaluator import (
    BehaviorContract,
    EvalObservation,
    check_contract,
    format_code_stats,
    observation_from_answer,
    to_feedback,
)
from app.evals.combine import combined_score
from app.evals.llm_judge import (
    ChatFn,
    JudgePrompt,
    judge_contract,
    judge_to_feedback,
    load_judge_prompt,
)
from app.factory import build_agent_pipeline

DATASET = "common_questions"
EXPERIMENT_PREFIX = "deepfin-badcase-code-llm"
RESULTS_DIR = ROOT / "evals" / "results"
JUDGE_PROMPT_PATH = ROOT / "evals" / "judge_prompts.yaml"

_RECORDS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _record(case_id: str, **fields: Any) -> None:
    with _LOCK:
        _RECORDS.setdefault(case_id, {"case_id": case_id}).update(fields)


def make_code_evaluator() -> Callable[..., list[dict[str, Any]]]:
    def code_evaluator(
        outputs: dict[str, Any],
        reference_outputs: dict[str, Any],
        inputs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        obs = EvalObservation.model_validate(outputs)
        contract = BehaviorContract.model_validate(reference_outputs)
        verdict = check_contract(obs, contract)
        _record(
            (inputs or {}).get("case_id", ""),
            question=(inputs or {}).get("question", ""),
            code_score=verdict.score,
            code_coverage=verdict.coverage,
            code_checks=[c.model_dump() for c in verdict.checks],
            tool_calls=obs.tool_calls,
            iterations=obs.iterations,
            citations=obs.citations,
            answer=obs.answer,
            tool_arguments=[a.model_dump() for a in obs.tool_arguments],
            evidence=[e.model_dump() for e in obs.evidence],
        )
        return to_feedback(verdict)

    return code_evaluator


def make_llm_evaluator(
    chat: ChatFn, p: JudgePrompt
) -> Callable[..., list[dict[str, Any]]]:
    def llm_judge_evaluator(
        outputs: dict[str, Any],
        reference_outputs: dict[str, Any],
        inputs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        obs = EvalObservation.model_validate(outputs)
        contract = BehaviorContract.model_validate(reference_outputs)
        question = str((inputs or {}).get("question", ""))
        # LangSmith 各 evaluator 独立执行、互不通信，judge 拿不到 code 层的
        # EvalVerdict；这里重算一次（纯函数，无额外网络代价）作为辅助观测。
        code_stats = format_code_stats(check_contract(obs, contract))
        verdict = judge_contract(
            obs, contract, question, chat, p, code_stats=code_stats
        )
        _record(
            (inputs or {}).get("case_id", ""),
            llm_status=verdict.status,
            llm_score=verdict.score,
            llm_behavior_aligned=verdict.behavior_aligned,
            llm_violations=verdict.violated_must_not,
            llm_mentions_satisfied=verdict.mentions_satisfied,
            llm_reason=verdict.reason or verdict.error,
            llm_error=verdict.error,
            judge_prompt_version=p.version,
        )
        return judge_to_feedback(verdict)

    return llm_judge_evaluator


def make_judge_chat(api_key: str, base_url: str, model: str) -> ChatFn:
    """原生 OpenAI 客户端（不经 wrap_openai）：judge 调用不进实验 trace。"""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(messages: list[dict[str, str]], temperature: float) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]  # openai SDK 重载不收裸 dict list，运行时兼容
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""

    return chat


def make_target(pipeline: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """LangSmith target：dataset inputs → Agent 真实链路 → 可观测事实。"""

    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        sid = uuid.uuid4().hex
        result = pipeline.answer(
            inputs["question"],
            history=list(inputs.get("history") or []),
            session_id=sid,
        )
        return observation_from_answer(result).model_dump()

    return target


def _combined(r: dict[str, Any]) -> float | None:
    """委托纯函数：代码层无可判项时只按 judge，judge 缺判不记失败。"""
    return combined_score(
        float(r.get("code_score") or 0.0),
        float(r.get("code_coverage") or 0.0),
        r.get("llm_status"),
        float(r.get("llm_score") or 0.0),
    )


def print_table() -> None:
    print("\n=== judge 判分 + 代码层统计表 ===")
    print(
        f"{'case':8} {'code':>5} {'cov':>5} {'llm':>5} "
        f"{'comb':>5} {'viol':>4}  status"
    )
    rows = sorted(_RECORDS.values(), key=lambda r: r["case_id"])
    for r in rows:
        comb = _combined(r)
        comb_s = "-" if comb is None else f"{comb:.2f}"
        violations = len(r.get("llm_violations") or [])
        print(
            f"{r['case_id']:8} {r.get('code_score', 0):>5.2f} "
            f"{r.get('code_coverage', 0):>5.2f} {r.get('llm_score', 0):>5.2f} "
            f"{comb_s:>5} {violations:>4}  {r.get('llm_status', 'missing')}"
        )
    if rows:
        scored = [c for c in (_combined(r) for r in rows) if c is not None]
        avg_code = sum(r.get("code_score", 0) for r in rows) / len(rows)
        avg_llm = sum(r.get("llm_score", 0) for r in rows) / len(rows)
        print(
            f"\n共 {len(rows)} 条 | 代码层均值 {avg_code:.2f} | judge 均值 {avg_llm:.2f}"
            f" | judge 通过 {sum(scored)}/{len(scored)}"
        )
        errors = [r["case_id"] for r in rows if r.get("llm_status") == "error"]
        if errors:
            print(f"judge 失败（不判通过）: {', '.join(errors)}")
        print("comb = judge 判分（代码层仅作统计，不参与判分）；- 表示 judge 未判到。")


def save_records() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"eval_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in sorted(_RECORDS.values(), key=lambda x: x["case_id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="四期评估实验：代码层 + LLM judge")
    ap.add_argument(
        "--dry-run", action="store_true", help="只打印计划，不调 LLM、不写云端"
    )
    ap.add_argument("--dataset", default=DATASET, help="LangSmith Dataset 名")
    ap.add_argument("--only", default="", help="只跑指定 case_id（逗号分隔）")
    ap.add_argument("--repetitions", type=int, default=1, help="每题跑几次（默认 1）")
    ap.add_argument(
        "--evaluators", default="code,llm", help="code / llm，逗号分隔（默认两者）"
    )
    ap.add_argument(
        "--from-results",
        default="",
        help="从本地 jsonl 重算汇总表（评估口径修订后无需重跑云端实验）",
    )
    ap.add_argument(
        "--judge-version",
        type=int,
        default=0,
        help="指定 judge prompt 版本（0 = 用 yaml 当前版本），用于旧口径复跑对比",
    )
    args = ap.parse_args()

    if args.from_results:
        path = Path(args.from_results)
        if not path.exists():
            print(f"错误：明细文件不存在 {path}")
            return 1
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    r = json.loads(line)
                    _RECORDS[r["case_id"]] = r
        print(f"从明细复算（不联网、不调 LLM）: {path}")
        print_table()
        return 0

    wanted_evaluators = {x.strip() for x in args.evaluators.split(",") if x.strip()}
    if not wanted_evaluators or not wanted_evaluators <= {"code", "llm"}:
        print("--evaluators 只能是 code / llm 的组合")
        return 1

    s = get_settings()
    os.environ.update(
        LANGSMITH_API_KEY=s.langsmith_api_key,
        LANGSMITH_ENDPOINT=s.langsmith_endpoint,
        LANGSMITH_PROJECT=s.langsmith_project,
    )
    from langsmith import Client

    c = Client()
    if not c.has_dataset(dataset_name=args.dataset):
        print(f"错误：Dataset {args.dataset} 不存在")
        return 1
    examples = list(c.list_examples(dataset_name=args.dataset))
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    if only:
        examples = [e for e in examples if (e.inputs or {}).get("case_id") in only]
    if not examples:
        print("没有匹配的 example")
        return 1

    p = load_judge_prompt(JUDGE_PROMPT_PATH, version=args.judge_version or None)
    print(
        f"Dataset: {args.dataset} | 本次 {len(examples)} 条 | 每题跑 {args.repetitions} 次"
    )
    print(
        f"评估器: {', '.join(sorted(wanted_evaluators))} | "
        f"judge prompt v{p.version} | judge model {s.deepseek_model}"
    )
    print("代码层: 工具序列 / 引用要求 / 编号越界；judge: 期望行为 / 禁止项 / 必提语义")
    for e in examples:
        print(
            f"  - {(e.inputs or {}).get('case_id', '?')}: {str((e.inputs or {}).get('question', ''))[:44]}"
        )
    if args.dry_run:
        print("dry-run：未调用 LLM、未创建 experiment")
        return 0
    if not (s.deepseek_api_key and s.langsmith_api_key):
        print("缺少 DEEPSEEK_API_KEY 或 LANGSMITH_API_KEY，无法跑真实链路")
        return 1

    from langsmith import evaluate

    pipeline = build_agent_pipeline()
    evaluators: list[Any] = []
    if "code" in wanted_evaluators:
        evaluators.append(make_code_evaluator())
    if "llm" in wanted_evaluators:
        chat = make_judge_chat(
            s.deepseek_api_key, s.deepseek_base_url, s.deepseek_model
        )
        evaluators.append(make_llm_evaluator(chat, p))
    results = evaluate(
        make_target(pipeline),
        data=examples,
        # langsmith 0.14.17 的 stub 只声明单 dict/RunEvaluator，运行时支持返回
        # feedback 列表（多个 key）；此处按实际行为保留，故局部豁免该类型检查。
        evaluators=evaluators,  # type: ignore[list-item]
        experiment_prefix=EXPERIMENT_PREFIX,
        description=f"四期：LLM judge v{p.version} 行为契约判分 + 代码层统计信号",
        num_repetitions=args.repetitions,
        max_concurrency=1,
        metadata={
            "dataset": args.dataset,
            "evaluator": "+".join(sorted(wanted_evaluators)),
            "judge_prompt_version": p.version,
            "judge_model": s.deepseek_model,
            "repetitions": args.repetitions,
            "phase": "B_semantic_judge",
        },
    )
    print(f"\nexperiment: {getattr(results, 'experiment_name', EXPERIMENT_PREFIX)}")
    print_table()
    path = save_records()
    print(f"明细已存: {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
