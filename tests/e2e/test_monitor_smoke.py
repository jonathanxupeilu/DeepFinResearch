"""市场监控 E2E 冒烟：真实 akshare 采集一轮并入库。

只依赖 akshare 网络能力，不依赖 API Key，故不设 skipif。
真实接口可能波动，断言从宽：run_all 返回 6 份报告即可，不强制有数据；
单源接口异常由 runner 的单源隔离兜住（报告 error 状态）。
"""

import pytest

from app.monitor.models import CollectReport, Dimension

pytestmark = [pytest.mark.e2e]


def test_monitor_collect_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITOR_DB_PATH", str(tmp_path / "monitor.db"))  # 隔离真实库
    from app.config import get_settings

    get_settings.cache_clear()  # 防 lru_cache 带入其他测试的假配置（参考 test_smoke）
    try:
        from app.factory import build_monitor_runner

        runner = build_monitor_runner()  # 构造成功即通过
        try:
            reports = runner.run_all()
            counts = runner.store.counts_by_dimension()
        finally:
            runner.store.close()

        assert len(reports) == 6
        assert all(isinstance(r, CollectReport) for r in reports)
        assert {r.dimension for r in reports} == set(Dimension)
        for r in reports:  # ok / error 均为合法状态
            assert r.ok or r.error
            print(f"{r.dimension.value}: ok={r.ok} added={r.added} error={r.error}")
        assert isinstance(counts, dict)
    finally:
        get_settings.cache_clear()  # teardown 恢复，避免污染后续测试
