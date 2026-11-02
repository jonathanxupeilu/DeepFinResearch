# tests/unit/test_citations.py
from app.pipeline.citations import build_citations

SOURCES = [("a.md", "巴菲特推崇护城河理论"), ("https://x.cn/1", "联网摘要")]


def test_filtered_by_markers():
    cites = build_citations("综合[1]与[2]的观点", SOURCES)
    assert [c.marker for c in cites] == [1, 2]
    assert cites[1].source == "https://x.cn/1"


def test_out_of_range_ignored():
    cites = build_citations("主要依据[1]（另见[5]）", SOURCES)
    assert [c.marker for c in cites] == [1]


def test_no_markers_keeps_all():
    cites = build_citations("模型没有按格式标注引用", SOURCES)
    assert [c.marker for c in cites] == [1, 2]


def test_empty_sources():
    assert build_citations("未找到足够信息[1]", []) == []
