# tests/unit/test_holdings.py
from app.monitor.holdings import load_holdings


def test_load_holdings(tmp_path):
    f = tmp_path / "holdings.json"
    f.write_text('[{"code": "600519", "name": "贵州茅台"}]', encoding="utf-8")
    hs = load_holdings(f)
    assert hs[0].code == "600519"
