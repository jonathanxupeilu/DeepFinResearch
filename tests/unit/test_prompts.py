# tests/unit/test_prompts.py
"""prompts.yaml 单一来源校验：prompts.py 暴露的常量全部来自 yaml 且非空。"""

from pathlib import Path

import yaml

import app.pipeline.prompts as p

_YAML_PATH = Path(p.__file__).with_name("prompts.yaml")


def _yaml_data() -> dict:
    with _YAML_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_yaml_has_expected_sections():
    data = _yaml_data()
    assert set(data) >= {"rag", "agent", "tools"}


def test_prompt_constants_loaded_from_yaml_nonempty():
    names = [
        "SYSTEM_PROMPT",
        "USER_TEMPLATE",
        "NO_CONTEXT_ANSWER",
        "SMALLTALK_ANSWER",
        "AGENT_SYSTEM_PROMPT",
        "KNOWLEDGE_SEARCH_DESCRIPTION",
        "KNOWLEDGE_SEARCH_QUERY_DESCRIPTION",
        "WEB_SEARCH_DESCRIPTION",
        "WEB_SEARCH_QUERY_DESCRIPTION",
        "WEB_SEARCH_TIME_RANGE_DESCRIPTION",
        "CURRENT_TIME_DESCRIPTION",
    ]
    for name in names:
        value = getattr(p, name)
        assert isinstance(value, str) and value.strip(), f"{name} 为空"


def test_prompt_constants_match_yaml_source():
    data = _yaml_data()
    assert p.SYSTEM_PROMPT == data["rag"]["system"]
    assert p.USER_TEMPLATE == data["rag"]["user_template"]
    assert p.NO_CONTEXT_ANSWER == data["rag"]["no_context_answer"]
    assert p.AGENT_SYSTEM_PROMPT == data["agent"]["system"]
    assert (
        p.KNOWLEDGE_SEARCH_DESCRIPTION
        == data["tools"]["knowledge_search"]["description"]
    )
    assert (
        p.WEB_SEARCH_TIME_RANGE_DESCRIPTION == data["tools"]["web_search"]["time_range"]
    )
    assert p.CURRENT_TIME_DESCRIPTION == data["tools"]["current_time"]["description"]


def test_user_template_keeps_placeholders():
    assert "{context}" in p.USER_TEMPLATE
    assert "{question}" in p.USER_TEMPLATE


def test_agent_prompt_guides_step_by_step_thinking():
    assert "逐步思考" in p.AGENT_SYSTEM_PROMPT
    assert "step by step" in p.AGENT_SYSTEM_PROMPT


def test_smalltalk_regex_still_works():
    assert p.is_smalltalk("你好")
    assert p.is_smalltalk("谢谢！")
    assert not p.is_smalltalk("什么是护城河？")
