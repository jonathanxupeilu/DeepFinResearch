# tests/unit/test_bad_cases.py
"""四期坏案例测评集：yaml 本体 + LangSmith Example 映射的结构契约。

坏案例与 questions.yaml 的区别：measures 是「行为边界」而非「答案质量」，
因此 outputs 必须是可断言的期望行为契约，不能是自然语言标准答案。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = ROOT / "evals" / "bad_cases.yaml"
PUSH_SCRIPT = ROOT / "scripts" / "push_bad_cases.py"

RETAINED = ["BC-09", "BC-10", "BC-11", "BC-12"]


def _load_push_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("push_bad_cases", PUSH_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def doc() -> dict:
    return yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mod() -> ModuleType:
    return _load_push_module()


def test_retained_cases_exactly_four(doc: dict) -> None:
    """用户 2026-11-06 复核确认：只保留 BC-09/10/11/12。"""
    assert [it["case_id"] for it in doc["items"]] == RETAINED


def test_each_case_has_required_fields(doc: dict) -> None:
    required = {
        "case_id",
        "failure_mode",
        "question",
        "history",
        "expected_behavior",
        "must_call_tools",
        "must_mention",
        "must_not",
        "citation_required",
        "severity",
        "evaluators",
        "human_required",
        "time_sensitive",
    }
    for it in doc["items"]:
        assert required <= set(it), f"{it['case_id']} 缺字段: {required - set(it)}"
        assert it["question"].strip()
        assert it["must_not"], "坏案例必须有可断言的禁止行为"
        assert it["severity"] in {"critical", "high", "medium", "low"}


def test_history_is_well_formed(doc: dict) -> None:
    for it in doc["items"]:
        assert isinstance(it["history"], list)
        for turn in it["history"]:
            assert turn["role"] in {"user", "assistant"}
            assert isinstance(turn["content"], str) and turn["content"].strip()


def test_safety_cases_require_human(doc: dict) -> None:
    """合规越界与证据不足硬答，只有人工能 pass。"""
    human = {it["case_id"] for it in doc["items"] if it["human_required"]}
    assert {"BC-10", "BC-11"} <= human


def test_to_example_matches_langsmith_three_boxes(doc: dict, mod: ModuleType) -> None:
    """Inputs / Reference Outputs / Metadata 与用户在网页端复核的措辞逐字对齐。"""
    for it in doc["items"]:
        ex = mod.to_example(it)
        assert set(ex) == {"inputs", "outputs", "metadata"}
        assert ex["inputs"] == {
            "case_id": it["case_id"],
            "question": it["question"],
            "history": it["history"],
        }, "Inputs 不得混入示例模板里的 user_id 等字段"
        assert ex["outputs"]["expected_behavior"] == it["expected_behavior"]
        assert ex["outputs"]["must_not"] == it["must_not"]
        assert ex["outputs"]["must_call_tools"] == it["must_call_tools"]
        assert ex["metadata"] == {
            "failure_mode": it["failure_mode"],
            "dataset_split": ["base"],
            "human_required": str(it["human_required"]).lower(),
        }, "metadata 须与用户在网页端已录的 6 条 schema 严格对齐"


def test_outputs_are_contract_not_answer(doc: dict, mod: ModuleType) -> None:
    """outputs 里不能出现「标准答案」类字段，否则 LLM judge 会退化成文本比对。"""
    for it in doc["items"]:
        outputs = mod.to_example(it)["outputs"]
        assert "answer" not in outputs
        assert "reference_answer" not in outputs
        assert isinstance(outputs["citation_required"], bool)


def test_dataset_targets_common_questions(doc: dict) -> None:
    """用户 2026-11-06 指定：写入已有的 common_questions，不另建数据集。"""
    assert doc["dataset"] == "common_questions"


def test_select_stale_ids_never_touches_existing_cases(mod: ModuleType) -> None:
    """幂等覆盖只能命中本次 4 条，用户手动录的 BC-01~06 一条都不能删。"""

    class FakeExample:
        def __init__(self, eid: str, case_id: str) -> None:
            self.id = eid
            self.inputs = {"case_id": case_id}

    existing = [FakeExample(f"e{i}", f"BC-{i:02d}") for i in range(1, 7)]
    existing += [FakeExample("x9", "BC-09"), FakeExample("x10", "BC-10")]
    stale = mod.select_stale_ids(existing, set(RETAINED))
    assert set(stale) == {"x9", "x10"}
    assert all(e.id not in stale for e in existing[:6])


def test_select_stale_ids_handles_missing_inputs(mod: ModuleType) -> None:
    class BareExample:
        def __init__(self) -> None:
            self.id = "bare"
            self.inputs = None

    assert mod.select_stale_ids([BareExample()], set(RETAINED)) == []
