# tests/unit/test_loaders.py
from pathlib import Path

import pytest

from app.ingest.loaders import SUPPORTED, load_file


def test_supported_formats():
    assert SUPPORTED == {".md", ".txt", ".pdf", ".docx"}


def test_load_md(tmp_path: Path):
    f = tmp_path / "a.md"
    f.write_text("# 标题\n正文", encoding="utf-8")
    assert "正文" in load_file(f)


def test_load_txt(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert load_file(f) == "hello"


def test_unsupported_extension(tmp_path: Path):
    f = tmp_path / "a.exe"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        load_file(f)


def test_load_docx(tmp_path: Path):
    from docx import Document as Docx

    f = tmp_path / "a.docx"
    d = Docx()
    d.add_paragraph("docx 正文内容")
    d.save(f)
    assert "docx 正文内容" in load_file(f)
