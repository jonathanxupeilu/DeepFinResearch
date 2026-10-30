# tests/unit/test_stats.py
from app.retrieval.stats import _category_of, _short_title, build_library_stats


def test_category_monitor_prefix():
    assert _category_of("monitor/持仓公告/abc123.md") == "市场监控"


def test_category_folder_prefix():
    assert _category_of("投资/2026/思考.md") == "投资"
    assert _category_of("历史/x.md") == "历史"


def test_category_upload_fallback():
    # 无目录成分的纯文件名 → 上传文档
    assert _category_of("投资思考.md") == "上传文档"


def test_short_title_strips_extension_and_truncates():
    assert _short_title("monitor/宏观指标/abc123.md") == "abc123"
    long_name = "a" * 40 + ".md"
    assert len(_short_title(long_name)) == 24


def test_build_stats_counts_articles_and_chunks():
    metas = [
        {"source": "a.md", "chunk_index": 0, "indexed_at": "2026-10-30T08:00:00+00:00"},
        {"source": "a.md", "chunk_index": 1, "indexed_at": "2026-10-30T08:00:00+00:00"},
        {"source": "b.md", "chunk_index": 0, "indexed_at": "2026-10-30T09:00:00+00:00"},
    ]
    stats = build_library_stats(metas)
    assert stats.articles == 2
    assert stats.chunks == 3


def test_build_stats_categories():
    metas = [
        {"source": "投资/a.md", "chunk_index": 0},
        {"source": "投资/b.md", "chunk_index": 0},
        {"source": "monitor/宏观指标/c.md", "chunk_index": 0},
    ]
    stats = build_library_stats(metas)
    assert stats.categories == {"投资": 2, "市场监控": 1}


def test_build_stats_latest_by_indexed_at():
    metas = [
        {"source": "old.md", "chunk_index": 0, "indexed_at": "2026-10-01T08:00:00+00:00"},
        {"source": "new.md", "chunk_index": 0, "indexed_at": "2026-10-30T09:00:00+00:00"},
    ]
    stats = build_library_stats(metas)
    assert stats.latest_title == "new"
    assert stats.latest_time is not None


def test_build_stats_missing_indexed_at_tolerated():
    # 存量数据无 indexed_at：不崩溃，latest 为 None
    metas = [{"source": "legacy.md", "chunk_index": 0}]
    stats = build_library_stats(metas)
    assert stats.articles == 1
    assert stats.latest_title is None
    assert stats.latest_time is None


def test_build_stats_empty():
    stats = build_library_stats([])
    assert stats.articles == 0
    assert stats.chunks == 0
    assert stats.categories == {}
    assert stats.latest_title is None
