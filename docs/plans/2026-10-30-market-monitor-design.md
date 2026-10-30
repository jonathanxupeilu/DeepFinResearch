# 二期工程：市场监控 — 详细设计

> 日期：2026-10-30 ｜ 依赖：一期 RAG 问答（v0.1.0 已交付） ｜ 状态：**已交付**（含当日 D010 提速优化，实施修订见 §11）

## 1. 需求回顾与已确认选型

每日监控市场信息面，前端面板展示；主界面改为左侧菜单导航（【投研顾问】= 一期对话能力，【市场监控】= 监控面板）。

| 决策点 | 选型 | 说明 |
|---|---|---|
| 数据源 | akshare 为主，Tavily 二批补舆情/热点 | 免费、接口全；Tavily 只预留接口位 |
| 调度 | **纯手动触发**（面板「立即采集」按钮） | 无常驻进程、无调度依赖 |
| LLM 加工 | **无**，只存原文按来源分类 | 零成本；重要度打标留到后续迭代 |
| 范围 | 核心 6 维度：持仓公告 / 每日要闻 / 宏观指标 / 美联储 / 重大会议 / 行业指标 | 舆情+热点事件二批随 Tavily 接入 |

**约束说明**：WorkBuddy 会话内的 neodata/通达信 connector 是会话工具，项目代码不可调用，故项目内采集统一走 akshare（版本钉死，接口变动频繁）。

## 2. 架构

```
config/holdings.json        持仓股列表（手工编辑，UI 只读展示）
        │
        ▼
[市场监控面板 · 立即采集] → runner.run_all()
                                │  按维度并发调用，单源失败不影响整体
                                ▼
        collectors/（统一 Collector 接口，按数据源插件化）
        ├─ announcements.py   持仓公告（akshare 巨潮公告接口，增量窗口回补）
        ├─ news.py            每日要闻（akshare 财联社，独立 20s 超时）
        ├─ macro.py           宏观指标（akshare：PMI/CPI/社融…）
        ├─ fed.py             美联储资产负债表等（akshare）
        ├─ policy.py          重大会议（静态日历文件 + 采集时比对）
        └─ industry.py        行业指标（akshare：金价/运价…）
                                │
                                ▼
        store.py  SQLite(data/monitor.db)
                  events 表：内容 hash 去重，按维度/时间索引
                  collect_state 表：每维度采集水位线（增量依据）
                  purge_before()：超 30 天旧事件自动清理
                                │
        面板展示 ←──────────────┘
        （可选按钮：事件文本入库知识库，复用一期 indexer）
```

## 3. 数据模型（Pydantic v2，禁裸 dict）

```python
class Dimension(str, Enum):
    ANNOUNCEMENT = "持仓公告"
    NEWS = "每日要闻"
    MACRO = "宏观指标"
    FED = "美联储"
    POLICY = "重大会议"
    INDUSTRY = "行业指标"

class MonitorEvent(BaseModel):
    dimension: Dimension
    title: str
    content: str = ""            # 摘要或指标数值文本
    url: str = ""
    source: str                  # akshare 接口名 / 手工
    published_at: datetime | None  # 部分指标无发布时间 → None
    collected_at: datetime       # 采集时间（自动）

class CollectReport(BaseModel):  # runner 汇总报告（面板展示采集状态）
    dimension: Dimension
    ok: bool
    added: int
    error: str | None = None
```

## 4. SQLite 存储（`app/monitor/store.py`）

```sql
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dimension TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    published_at TEXT,           -- ISO 格式，可为 NULL
    collected_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE  -- sha256(dimension+title+url+content)[:16]
);
CREATE INDEX IF NOT EXISTS idx_events_dim_time ON events(dimension, published_at DESC);
```

- **去重**：hash 冲突静默跳过（added 计数区分新增/跳过）
- **水位线**（D010 增）：`collect_state` 表记每维度上次成功采集时间；`get_last_collect/set_last_collect`；采集成功的维度才推进，失败维度下次重采
- **过时清理**（D010 增）：`purge_before(days) -> int` 删除 `collected_at` 早于 now-days 的事件，采集完成后 UI 自动调用（默认 30 天）并显示清理条数
- 接口：`save_events(events) -> (added, skipped)`、`list_events(dimension, limit)`、`counts_by_dimension()`、`get_last_collect/set_last_collect`、`purge_before`
- 真实 SQLite + tmp_path 做 integration 测试

## 5. 采集器设计（`app/monitor/collectors/`）

统一接口（Protocol，与一期 LLMClient 抽象同风格）：

```python
class Collector(Protocol):
    dimension: Dimension
    def collect(self, since: datetime | None = None) -> list[MonitorEvent]: ...
# since = 该维度上次成功采集水位线（runner 从 store 读取后传入）；
# 公告采集器用它收缩回补窗口，其余采集器透传忽略。首次采集传 None。
```

| Collector | akshare 接口（实施时验证可用性） | 备注 |
|---|---|---|
| announcements | `ak.stock_notice_report`（巨潮公告） | 只采 holdings.json 中的代码 |
| news | `ak.stock_info_global_cls`/`ak.stock_info_global_em` | 财联社+东财要闻，取其一或合并 |
| macro | `ak.macro_china_pmi` / `macro_china_cpi` 等 | 每指标一条事件，数值入 content |
| fed | `ak.news_economic_baidu`（财经日历）或 FOMC 静态表 | 接口不稳定则降级静态日历 |
| policy | **静态日历** `config/policy_calendar.json`（2026 已知会议日期） | 采集时比对"临近会议"生成提醒事件 |
| industry | 金价 `ak.spot_hist_sge`、运价 BDI 等 | 首批 2-3 个指标即可，可扩展 |

**容错约定**：每个 collector 内部 catch 全部异常并返回空列表 + 记录；`runner.run_all()` 汇总为 `CollectReport` 列表，面板显示每个维度采集状态（成功 N 条 / 失败原因）。

**runner 并发语义**（D010 增）：六源线程池并发执行（网络 IO 密集），入库/水位线更新在主线程串行；`run_all(on_report=...)` 支持完成即回调（UI 实时进度），返回值保持注入顺序与完成先后无关。

**分级超时**（D010 增）：基类 `_fetch_or_none` 带 ThreadPoolExecutor 超时保护（默认 60s）；新闻维度（财联社接口在本机网络持续挂起）在 factory 单独收紧为 20s。

**akshare 兼容策略**：版本钉死在 `pyproject.toml`；接口名以实施当日实测为准，设计文档中接口名为候选。实测偏差：`index_bdi_hist` 已被移除→迁移 `macro_shipping_bdi`；`spot_hist_sge` 列名变为 date/close。

## 6. 前端改造（`app/ui/`）

- `webapp.py` 改为 **`st.navigation` 多页**（每页显式 `url_path`，避免入口函数同名导致 pathname 冲突）：
  - `pages/advisor.py`：【投研顾问】— 聊天 + 侧边栏知识库管理 + **离线仓库概览卡片**（存量文章数/分类分布/最新入库短标题，数据来自切片元数据聚合 `app/retrieval/stats.py`；分类规则：`monitor/` 前缀→市场监控、目录前缀、纯文件名→上传文档）
  - `pages/monitor.py`：【市场监控】面板：
    - 顶部：「立即采集」按钮 → `runner.run_all(on_report=...)` → `st.status` 分维度实时进度 → 显示各维度 CollectReport
    - 采集完成后自动清理超 30 天旧事件并显示清理条数
    - 维度筛选（selectbox）+ 事件表格（时间/标题/来源/内容），按 `published_at` 倒序
    - 每维度计数徽标；空维度提示"尚未采集"
  - 启动即查库展示历史事件（无库自动建表）
- holdings.json 路径在侧边栏只读展示 + 提示手工编辑
- **入口约束不变**：`streamlit run app/ui/webapp.py`（多页后 webapp.py 成为入口壳）

## 7. 与一期衔接

- 监控事件**可选入库知识库**：面板每条事件带「入库」按钮 → 拼接为 md 文本 → 复用一期 `Indexer`（source 用 `monitor/{dimension}/{hash}.md`）→ 投研顾问即可检索引用
- `factory.py` 新增 `build_monitor_runner()`，与现有组装风格一致
- 一期所有现有测试不得回归

## 8. 测试策略（TDD）

| 层 | 内容 | 依赖 |
|---|---|---|
| unit | MonitorEvent/CollectReport 模型、policy 静态日历比对、hash 生成 | 全 mock |
| unit | runner 容错：单 collector 抛异常不影响其他维度 | mock collectors |
| integration | store 增删查、hash 去重、维度过滤、分页 | 真实 SQLite（tmp_path） |
| integration | 各 collector 用 akshare **录制回放**（fixture 存样本 JSON）| 无网络 |
| e2e | 真实 akshare 采集一轮全维度 + 入库（`@pytest.mark.e2e`，可 skip） | 网络 |

UI 不做自动化测试（Streamlit 特性），语法校验 + 手动冒烟。

## 9. 任务拆分预估（实施计划阶段细化）

约 8-9 个 TDD 任务：① 模型+配置加载 ② SQLite store ③ collector 接口+policy 静态日历 ④ 宏观/要闻/公告/美联储/行业 5 个采集器 ⑤ runner 容错聚合 ⑥ holdings 管理 ⑦ 前端导航改造 ⑧ 监控面板 ⑨ e2e+README+CHANGELOG。

## 10. 明确不做（YAGNI）

- 定时调度/APScheduler（用户已选手动）
- LLM 打标/摘要/重要度
- Tavily 舆情与热点事件采集器（仅留 Dimension 枚举扩展位与接口范式）
- 事件推送通知（邮件/IM）
- 历史指标图表化（面板只做列表展示）

## 11. 实施修订记录（2026-10-30，交付后回写）

1. **D010 采集提速四件套**（决策日志 D010）：① runner 串行改线程池并行 + `on_report` 完成即报；② `collect_state` 水位线 + 公告增量窗口；③ 新闻维度独立 20s 超时；④ 超 30 天事件自动清理。根因：财联社接口挂起吃满 60s、公告固定 7 天逐日全市场拉取、六源串行。预期 2 分钟 → 20-30 秒。
2. **文件名调整**：`fed_meetings.py`→`fed.py`、`policy_meetings.py`→`policy.py`（§2 架构图已同步）。
3. **e2e 实跑发现的 akshare 接口变更**：`index_bdi_hist` 移除→`macro_shipping_bdi`；`spot_hist_sge` 列名变为 date/close（§5 已同步）。
4. **投研顾问页概览卡片**：新增 `app/retrieval/stats.py`（纯函数统计）+ 切片元数据 `indexed_at` 时间戳；旧数据缺该字段由统计层兜底。
5. **修复**：`st.Page` 显式 `url_path`（双页面入口函数同名致 pathname 冲突）。
