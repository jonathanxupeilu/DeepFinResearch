# scripts/build_evals.py
"""四期 Evals：跑真实 Agent 链路，把基线答案与运行指标回填 evals/dataset.yaml。

用法见 evals/questions.yaml 头部注释。题目本体人工维护，dataset.yaml 是生成物。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.factory import build_agent_pipeline
from app.models import RagAnswer

QUESTIONS_PATH = ROOT / "evals" / "questions.yaml"
DATASET_PATH = ROOT / "evals" / "dataset.yaml"
LS_DATASET = "deepfin-evals-v1"

warnings.filterwarnings("ignore", category=DeprecationWarning)


def _load_questions() -> dict[str, Any]:
    with QUESTIONS_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _git_rev() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 探针脚本：拿不到 git 就留空
        return ""


def _metrics(result: RagAnswer) -> dict[str, Any]:
    steps = {t.step for t in result.trace}
    return {
        "iterations_used": max(steps) if steps else 0,
        "tool_calls": [t.tool for t in result.trace],
        # 检索词逐条留档：判分要点里的 retrieval_query_must_contain 靠它判
        "queries": [
            {
                "step": t.step,
                "tool": t.tool,
                "query": t.arguments.get("query")
                or t.arguments.get("time_range")
                or "",
            }
            for t in result.trace
        ],
        "citation_count": len(result.citations),
        "answer_chars": len(result.answer),
    }


def _langsmith_stats(sid: str, project: str, timeout_s: float = 40.0) -> dict[str, Any]:
    """按 session_id 回读 trace 取 LLM 次数与 token；子 run 走批量上报，需轮询到出现。"""
    from langsmith import Client

    c = Client()
    deadline = time.monotonic() + timeout_s
    root = None
    children: list[Any] = []
    while time.monotonic() < deadline:
        # 0.14.17 的 list_runs(name=/trace_id=/parent_run_id=) 过滤参数均不生效，
        # 只能全量扫描后客户端归组；子 run 继承父 metadata，故必须同时要求根节点
        runs = list(c.list_runs(project_name=project))
        root = next(
            (
                r
                for r in runs
                if r.name == "agent_answer"
                and r.parent_run_id is None
                and ((r.extra or {}).get("metadata") or {}).get("session_id") == sid
            ),
            None,
        )
        if root is not None:
            children = [r for r in runs if r.parent_run_id == root.id]
            if children:
                break
        time.sleep(3)
    if root is None:
        return {}
    llm_calls = [r for r in children if r.name == "ChatOpenAI"]
    tokens = sum(
        ((r.extra or {}).get("metadata") or {})
        .get("usage_metadata", {})
        .get("total_tokens", 0)
        or 0
        for r in children
    )
    try:
        url = c.get_run_url(run=root, project_name=project)
    except Exception:  # noqa: BLE001 探针脚本：URL 拿不到不影响基线
        url = ""
    return {
        "trace_id": str(root.id),
        "llm_calls": len(llm_calls),
        "tool_spans": sum(1 for r in children if r.name == "tool_run"),
        "total_tokens": tokens,
        "trace_url": url,
    }


def _run_item(pipeline: Any, item: dict[str, Any], project: str) -> dict[str, Any]:
    sid = uuid.uuid4().hex
    history = list(item.get("history") or [])
    t0 = time.perf_counter()
    result = pipeline.answer(item["question"], history=history, session_id=sid)
    latency = round(time.perf_counter() - t0, 2)

    baseline = _metrics(result)
    baseline["session_id"] = sid
    baseline["latency_s"] = latency
    baseline["answer"] = result.answer
    baseline.update(_langsmith_stats(sid, project))
    return {
        "id": item["id"],
        "category": item.get("category", ""),
        "question": item["question"],
        "history": history,
        "time_sensitive": bool(item.get("time_sensitive", False)),
        "expected": item.get("expected", {}),
        "baseline": baseline,
    }


def _push_to_langsmith(items: list[dict[str, Any]]) -> None:
    from langsmith import Client

    c = Client()
    if not c.has_dataset(dataset_name=LS_DATASET):
        c.create_dataset(
            LS_DATASET,
            description="四期 Evals：Agent 回答质量基线（由 scripts/build_evals.py 生成）",
        )
    wanted_ids = {it["id"] for it in items}
    stale = [
        e.id
        for e in c.list_examples(dataset_name=LS_DATASET)
        if (e.metadata or {}).get("item_id") in wanted_ids
    ]
    if stale:
        c.delete_examples(stale)
    c.create_examples(
        dataset_name=LS_DATASET,
        examples=[
            {
                "inputs": {
                    "id": it["id"],
                    "category": it["category"],
                    "question": it["question"],
                    "history": it["history"],
                    "time_sensitive": it["time_sensitive"],
                },
                "outputs": {
                    "expected": it["expected"],
                    "baseline_answer": it["baseline"].get("answer", ""),
                    "baseline_metrics": {
                        k: v
                        for k, v in it["baseline"].items()
                        if k not in ("answer", "trace_url")
                    },
                },
                "metadata": {"item_id": it["id"]},
            }
            for it in items
        ],
    )
    print(f"已推送 {len(items)} 条到 LangSmith Dataset: {LS_DATASET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="构建四期 Evals 基线数据集")
    ap.add_argument(
        "--dry-run", action="store_true", help="只打印计划，不调 LLM、不写文件"
    )
    ap.add_argument("--push", action="store_true", help="额外同步到 LangSmith Dataset")
    ap.add_argument(
        "--push-only",
        action="store_true",
        help="不调 LLM，把现有 evals/dataset.yaml 推到 LangSmith",
    )
    ap.add_argument("--only", default="", help="只跑指定 item id（逗号分隔）")
    args = ap.parse_args()

    data = _load_questions()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    items = [i for i in data["items"] if not wanted or i["id"] in wanted]

    s = get_settings()
    print(
        f"题目 {len(items)} 条 | 模型 {s.deepseek_model} | max_iterations {s.agent_max_iterations}"
    )
    for it in items:
        print(f"  - {it['id']:28s} {it['question'][:40]}")
    if args.dry_run:
        print("dry-run：未调用 LLM，未写文件")
        return 0

    os.environ.update(
        LANGSMITH_API_KEY=s.langsmith_api_key,
        LANGSMITH_ENDPOINT=s.langsmith_endpoint,
        LANGSMITH_PROJECT=s.langsmith_project,
    )
    if args.push_only:
        if not DATASET_PATH.exists():
            print("evals/dataset.yaml 不存在，先跑一次采集再推")
            return 1
        old_doc = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8"))
        _push_to_langsmith(old_doc["items"])
        return 0

    if not (s.deepseek_api_key and s.dashscope_api_key):
        print("缺少 DEEPSEEK/DASHSCOPE Key，无法跑真实链路")
        return 1

    pipeline = build_agent_pipeline()
    out: list[dict[str, Any]] = []
    for it in items:
        print(f"跑 {it['id']} …", flush=True)
        rec = _run_item(pipeline, it, s.langsmith_project)
        b = rec["baseline"]
        print(
            f"  轮数={b['iterations_used']} LLM={b.get('llm_calls')} tokens={b.get('total_tokens')} "
            f"引用={b['citation_count']} 耗时={b['latency_s']}s 工具={b['tool_calls']}"
        )
        out.append(rec)

    fresh = {r["id"]: r for r in out}
    keep_ids = {i["id"] for i in data["items"]}  # 题目改名/删除后，旧基线不留在文件里
    merged: list[dict[str, Any]] = []
    if DATASET_PATH.exists():
        old = yaml.safe_load(DATASET_PATH.read_text(encoding="utf-8")) or {}
        for it in old.get("items", []):
            if it["id"] in keep_ids:
                merged.append(fresh.get(it["id"], it))
    for r in out:  # --only 跑到新题目时追加
        if r["id"] not in {m["id"] for m in merged}:
            merged.append(r)

    doc = {
        "name": data["name"],
        "version": data["version"],
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_rev": _git_rev(),
        "config": {
            "model": s.deepseek_model,
            "agent_max_iterations": s.agent_max_iterations,
            "top_k": s.top_k,
            "score_threshold": s.score_threshold,
            "web_search_enabled": bool(s.tavily_api_key.strip()),
        },
        "items": merged,
    }
    with DATASET_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False, width=100)
    print(f"基线已写入 {DATASET_PATH}")

    if args.push:
        _push_to_langsmith(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
