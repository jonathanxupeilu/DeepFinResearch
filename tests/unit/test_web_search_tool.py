# tests/unit/test_web_search_tool.py
import httpx
import pytest

from app.tools import web_search as ws
from app.tools.web_search import WebSearchTool

RESPONSE_JSON = {
    "results": [
        {
            "title": "黄金创新高",
            "url": "https://n.cn/1",
            "content": "金价突破历史新高",
            "score": 0.9,
        },
        {
            "title": "美联储议息",
            "url": "https://n.cn/2",
            "content": "维持利率不变",
            "score": 0.8,
        },
    ]
}


class FakeResponse:
    def __init__(self, payload=None, status=200, raise_exc=None):
        self._payload = payload
        self.status_code = status
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)

    def json(self):
        return self._payload


def patch_post(monkeypatch, response):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setattr(ws.httpx, "post", fake_post)
    return captured


def test_empty_key_rejected():
    with pytest.raises(ValueError, match="TAVILY"):
        WebSearchTool(api_key="  ")


def test_spec_shape():
    spec = WebSearchTool(api_key="k").spec
    assert spec.name == "web_search"
    assert spec.parameters["required"] == ["query"]


def test_run_maps_results_to_evidence(monkeypatch):
    captured = patch_post(monkeypatch, FakeResponse(payload=RESPONSE_JSON))
    result = WebSearchTool(api_key="sk-key", max_results=3).run({"query": "黄金"})
    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["json"]["query"] == "黄金"
    assert captured["json"]["max_results"] == 3
    assert captured["headers"]["Authorization"] == "Bearer sk-key"
    assert len(result.evidence) == 2
    assert result.evidence[0].source == "https://n.cn/1"
    assert "金价突破历史新高" in result.evidence[0].text
    assert "黄金创新高" in result.text
    assert "https://n.cn/2" in result.text


def test_run_empty_results(monkeypatch):
    patch_post(monkeypatch, FakeResponse(payload={"results": []}))
    result = WebSearchTool(api_key="k").run({"query": "冷门"})
    assert result.evidence == []
    assert "未找到" in result.text


def test_run_http_error_degrades(monkeypatch):
    patch_post(
        monkeypatch,
        FakeResponse(
            status=401,
            raise_exc=httpx.HTTPStatusError("401", request=None, response=None),
        ),
    )
    result = WebSearchTool(api_key="k").run({"query": "x"})
    assert result.evidence == []
    assert "失败" in result.text


def test_run_network_error_degrades(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("连不上")

    monkeypatch.setattr(ws.httpx, "post", boom)
    result = WebSearchTool(api_key="k").run({"query": "x"})
    assert "失败" in result.text
    assert "连不上" in result.text


def test_run_missing_query_degrades(monkeypatch):
    patch_post(monkeypatch, FakeResponse(payload=RESPONSE_JSON))
    result = WebSearchTool(api_key="k").run({})
    assert result.evidence == []
    assert "query" in result.text


def test_run_passes_time_range_when_given(monkeypatch):
    captured = patch_post(monkeypatch, FakeResponse(payload=RESPONSE_JSON))
    WebSearchTool(api_key="k").run({"query": "黄金板块", "time_range": "week"})
    assert captured["json"]["time_range"] == "week"


def test_run_omits_time_range_when_absent(monkeypatch):
    captured = patch_post(monkeypatch, FakeResponse(payload=RESPONSE_JSON))
    WebSearchTool(api_key="k").run({"query": "黄金板块"})
    assert "time_range" not in captured["json"]


def test_spec_exposes_time_range():
    props = WebSearchTool(api_key="k").spec.parameters["properties"]
    assert "week" in props["time_range"]["enum"]
    assert WebSearchTool(api_key="k").spec.parameters["required"] == ["query"]


def test_run_malformed_result_items_skipped(monkeypatch):
    patch_post(
        monkeypatch,
        FakeResponse(
            payload={
                "results": [
                    {"title": "无url"},
                    {"url": "https://ok.cn", "content": "c"},
                ]
            }
        ),
    )
    result = WebSearchTool(api_key="k").run({"query": "x"})
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "https://ok.cn"
