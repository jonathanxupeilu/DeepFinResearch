# 二期市场监控 — 实施计划

> **For implementer:** Use TDD throughout. Write failing test first. Watch it fail. Then implement.

**Goal:** 市场监控核心 6 维度（手动采集）+ SQLite 存储 + Streamlit 双页导航（投研顾问/市场监控）+ 事件可入库知识库。

**Architecture:** `app/monitor/`（models/holdings/store/collectors/runner）与一期完全解耦，经 factory 接入；UI 拆为 `st.navigation` 多页。数据源 akshare（版本钉死），测试用 mock DataFrame 不联网。

**Tech Stack:** 新增 `akshare`（钉版本），其余复用一期。SQLite 标准库。

**设计文档:** `docs/plans/2026-10-30-market-monitor-design.md` ｜ **决策日志:** `docs/DECISIONS.md`（D008）

---

### Task 1: 监控数据模型与持仓配置

**Files:**
- Create: `app/monitor/__init__.py`, `app/monitor/models.py`, `app/monitor/holdings.py`, `config/holdings.json`（示例：600519/000858）
- Test: `tests/unit/test_monitor_models.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_monitor_models.py
from datetime import datetime
import pytest
from pydantic import ValidationError

from app.monitor.models import CollectReport, Dimension, MonitorEvent


def test_dimension_has_six_values():
    assert {d.value for d in Dimension} == {
        "持仓公告", "每日要闻", "宏观指标", "美联储", "重大会议", "行业指标",
    }


def test_monitor_event_auto_collected_at():
    e = MonitorEvent(dimension=Dimension.NEWS, title="央行降准", source="cls")
    assert e.collected_at is not None
    assert e.content == "" and e.url == ""


def test_monitor_event_requires_title_and_source():
    with pytest.raises(ValidationError):
        MonitorEvent(dimension=Dimension.NEWS, title="", source="cls")


def test_collect_report_defaults():
    r = CollectReport(dimension=Dimension.MACRO, ok=True, added=3)
    assert r.error is None
```

```python
# tests/unit/test_holdings.py
from app.monitor.holdings import load_holdings


def test_load_holdings(tmp_path):
    f = tmp_path / "holdings.json"
    f.write_text('[{"code": "600519", "name": "贵州茅台"}]', encoding="utf-8")
    hs = load_holdings(f)
    assert hs[0].code == "600519"
```

**Step 2:** FAIL → **Step 3: 实现**

`app/monitor/models.py`：`Dimension(str, Enum)` 六值；`MonitorEvent`（published_at 可 None，collected_at 默认 `datetime.now()`，title/source 非空校验）；`CollectReport(dimension, ok, added=0, error=None)`。

`app/monitor/holdings.py`：

```python
from pathlib import Path
from pydantic import BaseModel


class Holding(BaseModel):
    code: str
    name: str = ""


def load_holdings(path: Path = Path("config/holdings.json")) -> list[Holding]:
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Holding.model_validate(x) for x in data]
```

`config/holdings.json` 示例两条。**Step 4:** PASS → **Step 5:** `git commit -m "feat: 监控数据模型与持仓配置加载"`

---

### Task 2: SQLite 事件存储

**Files:**
- Create: `app/monitor/store.py`
- Test: `tests/integration/test_monitor_store.py`

**Step 1: 写失败测试**

```python
# tests/integration/test_monitor_store.py
from datetime import datetime

from app.monitor.models import Dimension, MonitorEvent
from app.monitor.store import EventStore


def make_event(title: str, dim=Dimension.NEWS) -> MonitorEvent:
    return MonitorEvent(dimension=dim, title=title, source="t",
                        published_at=datetime(2026, 10, 30, 9, 0))


def test_save_and_count(tmp_path):
    s = EventStore(tmp_path / "m.db")
    added, _ = s.save_events([make_event("a"), make_event("b")])
    assert added == 2 and s.count() == 2


def test_hash_dedup(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("同一事件")])
    added, skipped = s.save_events([make_event("同一事件")])
    assert added == 0 and skipped == 1 and s.count() == 1


def test_list_filter_by_dimension_desc(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("n1"), make_event("m1", Dimension.MACRO)])
    got = s.list_events(dimension=Dimension.MACRO)
    assert len(got) == 1 and got[0].title == "m1"


def test_counts_by_dimension(tmp_path):
    s = EventStore(tmp_path / "m.db")
    s.save_events([make_event("a"), make_event("b", Dimension.FED)])
    counts = s.counts_by_dimension()
    assert counts[Dimension.NEWS] == 1 and counts[Dimension.FED] == 1
```

**Step 2:** FAIL → **Step 3: 实现**（按设计文档 §4 建表 SQL；`content_hash = sha256(dimension+title+url+content)[:16]`，UNIQUE 约束 + `INSERT OR IGNORE` 区分 added/skipped；`list_events` 支持 dimension/limit，按 published_at DESC NULLS LAST、collected_at DESC；返回 `list[MonitorEvent]`）。

**Step 4:** PASS → **Step 5:** `git commit -m "feat: 监控事件 SQLite 存储（hash 去重/维度过滤）"`

---

### Task 3: Collector 接口与重大会议静态日历

**Files:**
- Create: `app/monitor/collectors/__init__.py`, `app/monitor/collectors/base.py`, `app/monitor/collectors/policy.py`, `config/policy_calendar.json`（2026 中央经济工作会议/两会等已知日期）
- Test: `tests/unit/test_policy_collector.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_policy_collector.py
from datetime import datetime, timedelta
from pathlib import Path

from app.monitor.models import Dimension
from app.monitor.collectors.policy import PolicyCollector


def make_calendar(tmp_path: Path, meeting_date: datetime) -> Path:
    f = tmp_path / "cal.json"
    f.write_text(
        f'[{{"date": "{meeting_date:%Y-%m-%d}", "name": "中央经济工作会议"}}]',
        encoding="utf-8",
    )
    return f


def test_upcoming_meeting_within_30_days(tmp_path):
    soon = datetime.now() + timedelta(days=10)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, soon))
    events = c.collect()
    assert events and events[0].dimension == Dimension.POLICY
    assert "中央经济工作会议" in events[0].title


def test_meeting_outside_window_skipped(tmp_path):
    far = datetime.now() + timedelta(days=90)
    c = PolicyCollector(calendar_path=make_calendar(tmp_path, far))
    assert c.collect() == []
```

**Step 2:** FAIL → **Step 3: 实现**（`Collector` Protocol：`dimension: Dimension`、`collect() -> list[MonitorEvent]`；PolicyCollector 读静态日历，窗口 [-1, +30] 天内会议生成事件，title=f"临近：{name}（{date}）"，source="policy_calendar"）。

**Step 4:** PASS → **Step 5:** `git commit -m "feat: Collector 接口与重大会议静态日历采集器"`

---

### Task 4: 宏观指标与每日要闻采集器（akshare）

**Files:**
- Create: `app/monitor/collectors/macro.py`, `app/monitor/collectors/news.py`
- Test: `tests/unit/test_macro_collector.py`, `tests/unit/test_news_collector.py`

**约定**：所有 akshare 采集器**构造时注入 akshare 模块**（默认 `import akshare as ak`），测试传 MagicMock 返回 pandas DataFrame——接口名若与实测不符只改默认参数/内部映射，测试结构不动。

**Step 1: 写失败测试**

```python
# tests/unit/test_macro_collector.py
import pandas as pd

from app.monitor.models import Dimension
from app.monitor.collectors.macro import MacroCollector


def fake_ak(magic):
    m = magic
    m.macro_china_pmi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "制造业-同比增长": [50.1]}
    )
    m.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    return m


def test_macro_collects_one_event_per_indicator():
    from unittest.mock import MagicMock
    c = MacroCollector(ak=fake_ak(MagicMock()))
    events = c.collect()
    assert len(events) == 2
    assert {e.dimension for e in events} == {Dimension.MACRO}
    assert "50.1" in events[0].content


def test_macro_failure_isolated():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.macro_china_pmi.side_effect = RuntimeError("接口挂了")
    ak.macro_china_cpi.return_value = pd.DataFrame(
        {"月份": ["2026年9月份"], "全国同比增长": [0.4]}
    )
    events = MacroCollector(ak=ak).collect()  # 单指标失败不炸整体
    assert len(events) == 1
```

```python
# tests/unit/test_news_collector.py
import pandas as pd

from app.monitor.models import Dimension
from app.monitor.collectors.news import NewsCollector


def test_news_collects_titles():
    from unittest.mock import MagicMock
    ak = MagicMock()
    ak.stock_info_global_cls.return_value = pd.DataFrame(
        {"标题": ["央行开展逆回购"], "内容": ["金额1000亿"], "发布时间": ["2026-10-30 09:00"]}
    )
    events = NewsCollector(ak=ak).collect()
    assert len(events) == 1
    assert events[0].dimension == Dimension.NEWS
    assert events[0].published_at is not None
```

**Step 2:** FAIL → **Step 3: 实现**

- `MacroCollector`：内部表 `[("PMI", ak.macro_china_pmi, 列映射), ("CPI", ...), ...]` 首批 PMI/CPI/社融 3 个；**逐指标 try/except**，取最新一行拼 content（`月份: 数值`），published_at 由月份解析（失败则 None）
- `NewsCollector`：`stock_info_global_cls`（财联社），列名实测校准；异常返回空列表

**Step 4:** PASS → **Step 5:** `git commit -m "feat: 宏观指标与每日要闻采集器（akshare mock 注入+单指标容错）"`

---

### Task 5: 持仓公告、美联储、行业指标采集器

**Files:**
- Create: `app/monitor/collectors/announcements.py`, `fed.py`, `industry.py`
- Test: `tests/unit/test_announcements_collector.py` 等 3 个

**要点**：
- `AnnouncementsCollector(holdings, ak)`：`ak.stock_notice_report(symbol="全部", date=近7日)`，按 holdings.code 过滤 title/代码列；列名以实测为准（测试用 mock DataFrame 固定映射）
- `FedCollector(ak)`：财经日历接口，过滤含 "FOMC/美联储/利率决议" 关键词的行；接口不可用时降级静态日历（同 Task 3 范式）——先按接口实现，实测不通时按既定降级方案改
- `IndustryCollector(ak)`：首批 2 个——黄金现货最新价、BDI 运价指数最新值；逐指标容错同 MacroCollector
- 测试全部 mock akshare，每采集器 ≥2 用例（正常采集 + 异常隔离）

**VERIFY:** PASS → `git commit -m "feat: 公告/美联储/行业指标采集器"`

---

### Task 6: Runner 聚合与容错

**Files:**
- Create: `app/monitor/runner.py`
- Test: `tests/unit/test_runner.py`

**Step 1: 写失败测试**

```python
# tests/unit/test_runner.py
from unittest.mock import MagicMock

from app.monitor.models import CollectReport, Dimension
from app.monitor.runner import MonitorRunner


def make_runner(collectors):
    store = MagicMock()
    store.save_events.side_effect = lambda evs: (len(evs), 0)
    return MonitorRunner(store=store, collectors=collectors), store


def test_run_all_aggregates_reports():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension, c1.collect = Dimension.NEWS, lambda: [MagicMock()]
    c2.dimension, c2.collect = Dimension.MACRO, lambda: [MagicMock()] * 3
    runner, _ = make_runner([c1, c2])
    reports = runner.run_all()
    assert all(isinstance(r, CollectReport) for r in reports)
    assert [r.added for r in reports] == [1, 3]


def test_single_collector_failure_isolated():
    c1, c2 = MagicMock(), MagicMock()
    c1.dimension = Dimension.NEWS
    c1.collect = MagicMock(side_effect=RuntimeError("网络炸了"))
    c2.dimension, c2.collect = Dimension.MACRO, lambda: []
    runner, _ = make_runner([c1, c2])
    reports = runner.run_all()
    assert reports[0].ok is False and "网络炸了" in reports[0].error
    assert reports[1].ok is True
```

**Step 2:** FAIL → **Step 3: 实现**（`MonitorRunner(store, collectors).run_all()`：逐 collector try/except → save_events → CollectReport；顺序执行——个人规模无需并发，YAGNI）。

**Step 4:** PASS → **Step 5:** `git commit -m "feat: MonitorRunner 聚合采集（单源失败隔离+采集报告）"`

---

### Task 7: factory 扩展监控组装

**Files:**
- Modify: `app/factory.py`（新增 `build_monitor_runner()`）、`app/monitor/collectors/__init__.py`（导出全部采集器）
- Test: `tests/unit/test_factory.py`（追加用例）

**要点**：
- `build_monitor_runner() -> MonitorRunner`：EventStore（`data/monitor.db`，Settings 可覆盖路径）+ 六个真实 collector（holdings 读 `config/holdings.json`，缺失时 holdings 为空列表并 warning，公告采集器空持仓→空结果不报错）
- 测试：monkeypatch CHROMA/DB 路径到 tmp_path + 环境变量 Key，断言返回 MonitorRunner 且 collectors 数量为 6
- `git commit -m "feat: factory 组装监控 runner（六采集器+SQLite store）"`

---

### Task 8: 前端导航改造（st.navigation 双页）

**Files:**
- Modify: `app/ui/webapp.py`（改为入口壳：项目根自举保留 + `st.navigation({"投研顾问": [advisor], "市场监控": [monitor]}).run()`）
- Create: `app/ui/pages/__init__.py`, `app/ui/pages/advisor.py`（原聊天+侧边栏知识库管理**原样迁移**，含 get_pipeline 缓存）, `app/ui/pages/monitor.py`（本任务先出骨架：标题+占位）
- Test: 无 UI 自动测试；语法校验 `ast.parse` + `pytest tests/unit tests/integration` 全绿（不回归）

**要点**：
- 迁移保持行为不变：session_state/messages/上传入库/聊天渲染原样搬进 advisor.py（页面函数形式，Streamlit Page API）
- 入口命令不变：`streamlit run app/ui/webapp.py`
- `git commit -m "feat: st.navigation 双页导航，聊天页迁移 advisor.py"`

---

### Task 9: 市场监控面板

**Files:**
- Modify: `app/ui/pages/monitor.py`

**功能清单**（无自动化测试，语法校验+手动冒烟）：
1. 「🔄 立即采集」按钮 → `st.spinner` 内 `build_monitor_runner().run_all()` → 展示 CollectReport 表格（维度/状态/新增条数/错误原因，失败行红色标记）
2. 维度筛选 selectbox（全部+6 维度）→ `EventStore.list_events()` 事件表（st.dataframe：时间/维度/标题/来源/内容截断），按时间倒序，默认 limit 100
3. 顶部 `counts_by_dimension()` 维度计数徽标（st.metric 行）
4. 每条事件「📥 入库知识库」按钮（expander 内）：拼接 md 文本（标题+内容+来源+URL）→ `Document(source=f"monitor/{dimension}/{hash}.md")` → 一期 Indexer → success/info 提示（复用 `build_ingest_components`）
5. holdings.json 路径只读提示（不存在时提示先创建）
6. 全部数据访问包 try/except → st.error 兜底（沿用一期 UI 容错风格）

**VERIFY:** 语法校验；`git commit -m "feat: 市场监控面板（采集/报告/事件列表/入库知识库）"`

---

### Task 10: E2E 冒烟 + README + CHANGELOG

**Files:**
- Create: `tests/e2e/test_monitor_smoke.py`（`@pytest.mark.e2e`：真实 akshare 采集一轮 → 入库 → 各维度计数 ≥0 且 runner 无未捕获异常；真实接口可能波动，断言从宽：run_all 返回 6 份报告即可，不强制有数据）
- Modify: `README.md`（二期章节：监控功能说明 + holdings.json 配置方法 + 手动采集用法）
- Modify: `docs/DECISIONS.md`（变更记录节追加二期条目）
- Modify: `docs/DECISIONS.md`（若实施中决策与 D008 有偏差，追加 D010 记录）

**VERIFY:**
- 无网络/无 Key 环境：`pytest tests/unit tests/integration -v` 全绿；`pytest tests/e2e -m e2e -v` 正确 skip 或按实际
- 质量门禁：`ruff check . --fix && black . && mypy app` 全过
- `git commit -m "feat: 二期 e2e 冒烟与文档收尾"`

---

## 完成标准（Definition of Done）

- [ ] `pytest tests/unit tests/integration` 全绿（不依赖网络与真实 akshare）
- [ ] `ruff check .` / `black --check .` / `mypy app` 零错误
- [ ] `streamlit run app/ui/webapp.py`：左侧菜单双页可切换；监控页点采集→报告展示→事件列表→一键入库知识库→投研顾问可检索引用
- [ ] 一期全部测试无回归（61+ 通过）
- [ ] DECISIONS（变更记录）/ README 同步
- [ ] 每个 Task 独立 commit

