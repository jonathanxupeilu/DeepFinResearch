# AGENT.md — DeepFinResearch 项目索引

> 面向 AI Agent / 新成员的项目导航。全局开发规范（编码/TDD/质量门禁/密钥管理）见 `~/.qoder-cn/agents.md`，本文件只做**项目级索引**：改哪个文件前，先在这里找到它是什么、归哪期管、对应哪份文档。

## 项目是什么

本地知识库 RAG 投研问答助手，六期路线图演进为多 Agent 投研平台。当前状态：**一、二期已完成**（151 unit/integration 测试绿 + e2e 冒烟）。

## 路线图（v2，六期）

| 期 | 内容 | 状态 |
|---|---|---|
| 一期 | 本地 RAG 问答（入库→检索→prompt→LLM 带引用）+ Streamlit/CLI | ✅ 完成 |
| 二期 | 市场监控面板（公告/要闻/宏观/美联储/会议/行业 6 维度），左菜单双页导航 | ✅ 完成 |
| 三期 | 工具调用 + ReAct 自主决策（取代一期闲聊正则分流） | 未启动 |
| 四期 | 记忆与上下文管理（短期/长期，ContextBuilder） | 未启动 |
| 五期 | 多 Agent 编排（芒格/施洛斯/巴菲特/邓普顿/马克斯五种投资思维角色） | 未启动 |
| 六期 | 财报/研报深度解读 + PTC 确定性财务计算（DCF/清算价值） | 未启动 |

## 文档索引

| 文档 | 内容 | 何时读 |
|---|---|---|
| `docs/plans/2026-10-29-local-rag-qa-design.md` | 总设计：一期架构 + 二至六期展望（含监控、ReAct、记忆、多Agent、PTC） | 动任何架构、规划新期、判断"某功能该放哪层"时 |
| `docs/plans/2026-10-29-local-rag-qa-phase1.md` | 一期实施计划：13 个 TDD 任务全文（含每个任务的测试与实现代码） | 改一期代码前对照原始规格；新任务参考其格式 |
| `docs/plans/2026-10-30-market-monitor-design.md` | 二期设计：6 维度采集/存储/双页 UI（§11 为实施修订记录） | 改 monitor 相关代码前 |
| `docs/plans/2026-10-30-market-monitor-phase2.md` | 二期实施计划：10 个 TDD 任务全文 | 改二期代码前对照原始规格 |
| `docs/DECISIONS.md` | **决策日志**（D001-D010，只增不改）+ 变更记录 | 任何改动前先看有没有相关决策；做完改动要回写 |
| `README.md` | 快速开始：安装、配置 .env、启动命令 | 环境搭建 |

## 代码索引

### 入口（改前先懂 factory）

| 文件 | 职责 |
|---|---|
| `app/factory.py` | **依赖组装唯一入口**：build_pipeline / build_ingest_components / build_monitor_store / build_monitor_runner。所有组件在此接线，UI/CLI 共用 |
| `app/ui/webapp.py` | Streamlit 入口壳：`st.navigation` 双页（每页显式 url_path）。⚠️ 文件不能叫 app.py——会遮蔽 app 包 |
| `app/ui/pages/advisor.py` | 【投研顾问】聊天 + 侧边栏上传入库 + 离线仓库概览卡片 |
| `app/ui/pages/monitor.py` | 【市场监控】面板：立即采集（st.status 实时进度）/ 事件列表 / 一键入库 |
| `app/cli.py` | 终端 REPL 问答（`python -m app.cli`），运行时容错 + 缺 Key 友好提示 |

### 核心链路（一次提问的数据流）

```
cli.py / webapp.py → factory → pipeline/rag.py → retrieval/retriever.py → retrieval/store.py (Chroma)
                                        ↓ prompt 组装（唯一收口）
                                  llm/client.py (DeepSeek)
```

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/pipeline/rag.py` | 检索→prompt→LLM→RagAnswer 带引用；空检索诚实拒答；闲聊分流 | **一期所有 prompt 组装收口于此**，三期 ReAct/五期多Agent 都在此扩展，不得旁路 |
| `app/pipeline/prompts.py` | SYSTEM_PROMPT / USER_TEMPLATE / 拒答文案 / 闲聊正则 | 所有面向用户的文案常量放这里，不散落 |
| `app/retrieval/retriever.py` | top-k 检索 + cosine 相似度阈值过滤 | score = 1 - cosine_dist，collection 必须是 cosine 空间 |
| `app/retrieval/store.py` | Chroma 封装（upsert/query/delete/按 source 管理/get_all_metadatas） | 创建集合须带 `metadata={"hnsw:space": "cosine"}` |
| `app/retrieval/stats.py` | 离线仓库统计（纯函数）：文章数/分类/最新入库；分类=monitor前缀→市场监控>目录前缀>上传文档 | 只聚合不查库；缺 indexed_at 的旧数据兜底 |
| `app/llm/client.py` | LLMClient Protocol + DeepSeekClient | 走接口抽象，三期 ReAct 换实现不改上层 |
| `app/llm/embedding.py` | DashScope embedding（分批 10 条/重试/截断） | 重试仅限 RateLimitError/APIConnectionError + reraise=True |

### 入库链路（上传文档的数据流）

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/ingest/loaders.py` | md/txt/pdf/docx → 纯文本 | 六期财报表格解析在此替换/扩展 |
| `app/ingest/splitter.py` | 段落聚合切片 + 超长硬切带 overlap | 参数校验拦截非正值 |
| `app/ingest/indexer.py` | hash 去重 + 版本替换 + 切片入库 | ids 必须含 source；元数据带 indexed_at（统计卡片依赖） |

### 市场监控（二期）

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/monitor/models.py` | Dimension 六值枚举 / MonitorEvent / CollectReport | 新维度先扩枚举 |
| `app/monitor/store.py` | SQLite：events 表（hash 去重）+ collect_state 水位线 + purge_before 过时清理 | 水位线只在采集成功后推进 |
| `app/monitor/collectors/base.py` | Collector Protocol（`collect(since=...)`）+ AkshareCollector 基类（超时保护/日期解析） | 超时默认 60s；naive 时间按北京时间转 UTC |
| `app/monitor/collectors/*.py` | 6 个采集器（公告支持增量窗口，新闻 20s 独立超时） | 单源异常降级空结果，不抛出 |
| `app/monitor/runner.py` | 线程池并行执行，on_report 完成即报，返回保持注入顺序 | 入库/水位线在主线程 |
| `scripts/probe_collectors.py` | 真实接口采集探针（冒烟/排查列名用） | 直连 akshare，会联网 |

### 基础设施

| 文件 | 职责 |
|---|---|
| `app/config.py` | Pydantic Settings 读 .env（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY 及全部可调参数） |
| `app/models.py` | Pydantic v2 模型：Document/Chunk/RetrievedChunk/Citation/RagAnswer——**禁裸 dict 传核心业务数据** |

## 测试索引

| 目录 | 覆盖 | 依赖 |
|---|---|---|
| `tests/unit/` | 一期（config/models/splitter/loaders/embedding/llm_client/rag_pipeline/factory/cli）+ 二期（monitor 模型/runner 并行容错/各采集器/stats） | 无网络、无 Key |
| `tests/integration/` | store/retriever/indexer（真实 Chroma，tmp_path）+ monitor store（真实 SQLite） | 无 Key |
| `tests/e2e/test_smoke.py` | 全链路入库→检索→问答（真实 API） | 需 .env 双 Key，无 Key 自动 skip |

```bash
# 常用命令（Windows, Git Bash）
.venv/Scripts/python.exe -m pytest tests/unit tests/integration -v   # 全量无 Key 测试
.venv/Scripts/python.exe -m pytest tests/e2e -m e2e -v               # 真实 API 冒烟
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m black --check . && .venv/Scripts/python.exe -m mypy app
.venv/Scripts/python.exe -m streamlit run app/ui/webapp.py           # 网页版
.venv/Scripts/python.exe -m app.cli                                  # 终端版
```

## 运行须知

- **装包必须用 uv**（`~/.local/bin/uv.exe`，清华+阿里镜像已持久化）；venv 内 pip 走不了代理
- `.env` 不入 git；`data/`（chroma 持久化 + monitor.db）、`knowledge/`（用户文档）同样不入 git
- 新增功能的任务格式参照 `2026-10-29-local-rag-qa-phase1.md`：失败测试→最小实现→提交
- 旧 backlog 三项已清（embedding 截断保护 / citations 精确解析 / st.cache_resource 已用于 pipeline 与 vector store）
- 监控事件默认保留 30 天（`monitor.py` 的 `_RETENTION_DAYS`），公告增量窗口最长回补 7 天
- akshare 接口变动频繁：改采集器前先跑 `scripts/probe_collectors.py` 对真实接口验证列名
