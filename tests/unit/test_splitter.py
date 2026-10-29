# tests/unit/test_splitter.py
import pytest

from app.ingest.splitter import TextSplitter


def test_short_text_single_chunk():
    s = TextSplitter(chunk_size=500, chunk_overlap=100)
    assert s.split("短文本") == ["短文本"]


def test_long_text_hard_cut_with_overlap():
    s = TextSplitter(chunk_size=100, chunk_overlap=20)
    chunks = s.split("字" * 250)
    assert len(chunks) == 3
    assert chunks[0][-20:] == chunks[1][:20]  # 相邻切片有重叠


def test_paragraph_merge_not_exceed_size():
    s = TextSplitter(chunk_size=50, chunk_overlap=0)
    text = "\n".join("段" * 10 for _ in range(6))
    for c in s.split(text):
        assert len(c) <= 50


def test_empty_and_whitespace():
    s = TextSplitter(chunk_size=100, chunk_overlap=10)
    assert s.split("") == []
    assert s.split("  \n\n  ") == []


def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=50, chunk_overlap=50)


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=0, chunk_overlap=0)
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=-50, chunk_overlap=0)


def test_invalid_negative_overlap_raises():
    with pytest.raises(ValueError):
        TextSplitter(chunk_size=50, chunk_overlap=-10)
