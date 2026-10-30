# tests/unit/test_holdings.py
import pytest
from pydantic import ValidationError

from app.monitor.holdings import Holding, load_holdings


def test_load_holdings(tmp_path):
    f = tmp_path / "holdings.json"
    f.write_text('[{"code": "600519", "name": "贵州茅台"}]', encoding="utf-8")
    hs = load_holdings(f)
    assert hs[0].code == "600519"
    assert hs[0].name == "贵州茅台"


def test_load_holdings_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_holdings(tmp_path / "missing.json")


def test_load_holdings_rejects_non_array(tmp_path):
    f = tmp_path / "holdings.json"
    f.write_text('{"code": "600519"}', encoding="utf-8")
    with pytest.raises(ValueError, match="JSON 数组"):
        load_holdings(f)


def test_holding_rejects_blank_code():
    with pytest.raises(ValidationError):
        Holding(code="   ")
