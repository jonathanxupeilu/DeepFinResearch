# scripts/push_bad_cases.py
"""四期坏案例：把 evals/bad_cases.yaml 推到 LangSmith 的 common_questions 数据集。

用法见 evals/bad_cases.yaml 头部注释。默认追加且跳过已存在的 case_id，
绝不删除用户在网页端手动录入的 BC-01~06；只有显式 --replace 才按 case_id 覆盖。
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings

CASES_PATH = ROOT / "evals" / "bad_cases.yaml"


def load_cases() -> dict[str, Any]:
    with CASES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_example(item: dict[str, Any]) -> dict[str, Any]:
    """一条坏案例 → LangSmith Example 三框，schema 与网页端已录的 6 条一致。"""
    return {
        "inputs": {
            "case_id": item["case_id"],
            "question": item["question"],
            "history": item["history"],
        },
        "outputs": {
            "expected_behavior": item["expected_behavior"],
            "must_call_tools": item["must_call_tools"],
            "must_mention": item["must_mention"],
            "must_not": item["must_not"],
            "citation_required": item["citation_required"],
            "severity": item["severity"],
        },
        "metadata": {
            "failure_mode": item["failure_mode"],
            "dataset_split": ["base"],
            "human_required": str(item["human_required"]).lower(),
        },
    }


def case_id_of(example: Any) -> str | None:
    inputs = getattr(example, "inputs", None) or {}
    cid = inputs.get("case_id")
    return str(cid) if cid else None


def select_stale_ids(examples: Iterable[Any], wanted: set[str]) -> list[str]:
    """只挑出本次 case_id 命中的 example；其他条目（含用户手录）一律不动。"""
    return [
        str(getattr(e, "id", ""))
        for e in examples
        if case_id_of(e) in wanted and getattr(e, "id", None)
    ]


def push(dataset_name: str, items: list[dict[str, Any]], replace: bool) -> int:
    from langsmith import Client

    s = get_settings()
    os.environ.update(
        LANGSMITH_API_KEY=s.langsmith_api_key,
        LANGSMITH_ENDPOINT=s.langsmith_endpoint,
        LANGSMITH_PROJECT=s.langsmith_project,
    )
    c = Client()
    if not c.has_dataset(dataset_name=dataset_name):
        print(f"错误：Dataset {dataset_name} 不存在，未推送（避免误建同名数据集）")
        return 1

    existing = list(c.list_examples(dataset_name=dataset_name))
    print(f"目标 Dataset: {dataset_name} | 现有 {len(existing)} 条")
    wanted = {it["case_id"] for it in items}
    present = {
        cid for e in existing if (cid := case_id_of(e)) is not None and cid in wanted
    }

    if replace:
        stale = select_stale_ids(existing, wanted)
        if stale:
            c.delete_examples(stale)
            print(f"--replace：覆盖旧 example {len(stale)} 条")
        pending = items
    else:
        if present:
            print(f"已存在，跳过：{', '.join(sorted(present))}")
        pending = [it for it in items if it["case_id"] not in present]

    if not pending:
        print("无新增，未改动云端数据")
        return 0

    c.create_examples(
        dataset_name=dataset_name,
        examples=[to_example(it) for it in pending],
    )
    print(f"已推送 {len(pending)} 条：{', '.join(it['case_id'] for it in pending)}")

    after = list(c.list_examples(dataset_name=dataset_name))
    ids_after = {case_id_of(e) for e in after}
    missing = wanted - ids_after
    print(f"回读校验：Dataset 现有 {len(after)} 条 | 本次 4 条齐全: {not missing}")
    return 0 if not missing else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="推送四期坏案例到 LangSmith")
    ap.add_argument("--dry-run", action="store_true", help="只打印预览，不联网")
    ap.add_argument(
        "--replace", action="store_true", help="按 case_id 覆盖已存在的 example"
    )
    ap.add_argument("--dataset", default="", help="覆盖 yaml 里的 dataset 名")
    args = ap.parse_args()

    doc = load_cases()
    items = doc["items"]
    dataset_name = args.dataset or doc["dataset"]
    print(f"坏案例 {len(items)} 条 → Dataset: {dataset_name}")
    for it in items:
        print(
            f"  - {it['case_id']}  {it['failure_mode']}  human={it['human_required']}"
        )
        print(f"      q: {it['question'][:46]}")

    if args.dry_run:
        print("dry-run：未联网、未写云端")
        return 0
    return push(dataset_name, items, args.replace)


if __name__ == "__main__":
    raise SystemExit(main())
