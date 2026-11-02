# AGENT.md — DeepFinResearch 项目索引

> 面向 AI Agent / 新成员的项目导航。全局开发规范（编码/TDD/质量门禁/密钥管理）见 `~/.qoder-cn/agents.md`，本文件只做**项目级索引**：改哪个文件前，先在这里找到它是什么、归哪期管、对应哪份文档。

## 项目是什么

本地知识库 RAG 投研问答助手，六期路线图演进为多 Agent 投研平台。当前状态：**一至三期已完成**（207 unit/integration 测试绿 + e2e 冒烟含真实 function calling 链路）。

## 路线图（v2，六期）

| 期 | 内容 | 状态 |
|---|---|---|
| 一期 | 本地 RAG 问答（入库→检索→prompt→LLM 带引用）+ Streamlit/CLI | ✅ 完成 |
| 二期 | 市场监控面板（公告/要闻/宏观/美联储/会议/行业 6 维度），左菜单双页导航 | ✅ 完成 |
| 三期 | 工具调用 + ReAct 自主决策（AgentPipeline，取代一期闲聊正则分流） | ✅ 完成 |
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
| `docs/plans/2026-11-02-agent-react-design.md` | 三期设计：工具层/ReAct 循环/证据编号/降级策略（§10 决策摘要） | 改 agent/tools/llm client 前 |
| `docs/plans/2026-11-02-agent-react-phase3.md` | 三期实施计划：9 个 TDD 任务全文 | 改三期代码前对照原始规格 |
| `docs/DECISIONS.md` | **决策日志**（D001-D017，只增不改）+ **踩坑记录**（唯一记录处，D017）+ 变更记录 | 任何改动前先看有没有相关决策；做完改动/踩坑要回写 |
| `README.md` | 快速开始：安装、配置 .env、启动命令 | 环境搭建 |

## 代码索引

### 入口（改前先懂 factory）

| 文件 | 职责 |
|---|---|
| `app/factory.py` | **依赖组装唯一入口**：build_pipeline / build_agent_pipeline / build_ingest_components / build_monitor_store / build_monitor_runner。所有组件在此接线，UI/CLI 共用 |
| `app/ui/webapp.py` | Streamlit 入口壳：`st.navigation` 双页（每页显式 url_path）+ 隐藏别名页保住 /advisor 直达路由。⚠️ 文件不能叫 app.py——会遮蔽 app 包；⚠️ 页面目录必须叫 `views/` 不能叫 `pages/`——pages/ 是 Streamlit 魔法目录，冷启动直达 URL 会绕过 st.navigation 落到目录多页 fallback（空白页） |
| `app/ui/views/advisor.py` | 【投研顾问】Agent 聊天（决策轨迹 expander + URL 引用链接）+ 右上「历史对话」折叠面板（与概览卡片同行、会话归档/点击续聊）+ 侧边栏上传入库 + 离线仓库概览卡片 |
| `app/ui/views/monitor.py` | 【市场监控】面板：「📈 指标趋势」折线图顶部默认展示（双列、近1/3/5/10年、最新值标注）/ 立即采集（st.status 实时进度）/ 事件列表（仅公告/要闻/美联储/会议 4 维度）/ 一键入库 |
| `app/cli.py` | 终端 REPL 问答（`python -m app.cli`，走 AgentPipeline，打印决策轨迹），运行时容错 + 缺 Key 友好提示 |

### 核心链路（一次提问的数据流）

```
cli.py / webapp.py → factory ─→ pipeline/agent.py（三期默认入口，ReAct 循环）
                                │    ↓ tools/ 工具注册表（knowledge_search→retriever；web_search→Tavily）
                                └─→ pipeline/rag.py（单轮 RAG 快速通道，e2e 基线）
                                        ↓ prompt 组装（pipeline 包唯一收口）
                                  llm/client.py (DeepSeek, chat / chat_with_tools)
```

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/pipeline/agent.py` | 三期 AgentPipeline：function calling ReAct 循环、全局证据编号 [n]、未知工具/失败容错、max_iterations 熔断后强制终答 | 与 rag.py 并列为 prompt 收口；系统提示词静态常量（时间靠 current_time 工具，D016）；五期多 Agent 在此注入角色 system_prompt |
| `app/pipeline/rag.py` | 检索→prompt→LLM→RagAnswer 带引用；空检索诚实拒答；闲聊分流 | 单轮快速通道（e2e 基线），Agent 入口已废除闲聊正则 |
| `app/pipeline/prompts.py` | **全部 prompt 唯一修改入口**：SYSTEM_PROMPT / AGENT_SYSTEM_PROMPT / USER_TEMPLATE / 拒答文案 / 闲聊正则 / 三个工具的 description 与参数描述常量 | 调优任何话术只改此文件；不散落 |
| `app/pipeline/citations.py` | 引用构建共享逻辑（按 [n] 标注过滤/越界忽略/无标注保留全部） | rag 与 agent 共用，改语义两处同时生效 |
| `app/tools/base.py` | Tool Protocol + ToolSpec/ToolResult/Evidence（Pydantic） | 工具内部 catch 全部异常降级失败文本；Evidence 不编号，编号归循环层 |
| `app/tools/registry.py` | ToolRegistry：注册（重名拒绝）/get/openai_tools() | 新工具 = 一个类 + factory 注册一行 |
| `app/tools/knowledge_search.py` | 包装一期 Retriever 的知识库检索工具 | query 必填，检索空/异常均降级观察文本 |
| `app/tools/current_time.py` | 当前北京时间+星期（无参数）；时间词问题由 Agent 自主调用锚定「最近」 | 注入时钟返回 UTC，+8 换算归工具；factory 无条件注册 |
| `app/tools/web_search.py` | Tavily REST 联网搜索（httpx，Bearer 鉴权，15s 超时，time_range 时间窗） | 空 Key 构造即拒绝；factory 只在有 Key 时注册 |
| `app/retrieval/retriever.py` | top-k 检索 + cosine 相似度阈值过滤 | score = 1 - cosine_dist，collection 必须是 cosine 空间 |
| `app/retrieval/store.py` | Chroma 封装（upsert/query/delete/按 source 管理/get_all_metadatas） | 创建集合须带 `metadata={"hnsw:space": "cosine"}` |
| `app/retrieval/stats.py` | 离线仓库统计（纯函数）：文章数/分类/最新入库；分类=monitor前缀→市场监控>目录前缀>上传文档 | 只聚合不查库；缺 indexed_at 的旧数据兜底 |
| `app/llm/client.py` | LLMClient Protocol + DeepSeekClient：chat / chat_with_tools（ToolCall/ChatResponse） | 走接口抽象；工具参数非法 JSON 降级空参；重试仅限限流/连接类 |
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
| `app/monitor/models.py` | Dimension 六值枚举 / MonitorEvent（含 `value` 指标数值）/ CollectReport | 新维度先扩枚举；事件类 value=None |
| `app/monitor/store.py` | SQLite：events 表（hash 去重、value 列 ALTER 迁移）+ collect_state 水位线 + purge_before 过时清理（exclude 豁免指标类）+ purge_empty_url 存量清理 | 水位线只在采集成功后推进；改 hash 算法会使存量失效，禁止 |
| `app/monitor/collectors/base.py` | Collector Protocol（`collect(since=...)`）+ AkshareCollector 基类（超时保护/日期解析） | 超时默认 60s；naive 时间按北京时间转 UTC |
| `app/monitor/collectors/*.py` | 6 个采集器（公告增量窗口；新闻东财主源+新浪 fallback、20s 独立超时；宏观/行业首次拉近10年序列、此后按 since 水位线回看90天增量；美联储正文含公布/预期/前值/重要性；全维度带来源链接） | 单源异常降级空结果，不抛出 |
| `app/monitor/runner.py` | 线程池并行执行，on_report 完成即报，返回保持注入顺序 | 入库/水位线在主线程 |
| `scripts/probe_collectors.py` | 真实接口采集探针（冒烟/排查列名用） | 直连 akshare，会联网 |

### 基础设施

| 文件 | 职责 |
|---|---|
| `app/config.py` | Pydantic Settings 读 .env（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY 必填；TAVILY_API_KEY 可选=空则不注册 web_search；agent_max_iterations 等全部可调参数） |
| `app/models.py` | Pydantic v2 模型：Document/Chunk/RetrievedChunk/Citation/TraceStep/RagAnswer（含 trace）/ChatMessage/ChatSession——**禁裸 dict 传核心业务数据** |
| `app/chat_store.py` | 历史对话存储：JSON 单文件会话持久化（同 id upsert、updated_at 倒序、原子写），advisor 页「历史对话」面板续聊数据源 |

## 测试索引

| 目录 | 覆盖 | 依赖 |
|---|---|---|
| `tests/unit/` | 一期（config/models/splitter/loaders/embedding/llm_client/rag_pipeline/factory/cli）+ 二期（monitor 模型/runner 并行容错/各采集器/stats）+ 三期（citations/tool_registry/knowledge_search/web_search/agent_pipeline/advisor 页 AppTest） | 无网络、无 Key |
| `tests/integration/` | store/retriever/indexer（真实 Chroma，tmp_path）+ monitor store（真实 SQLite） | 无 Key |
| `tests/e2e/test_smoke.py` | 全链路入库→检索→问答（真实 API） | 需 .env 双 Key，无 Key 自动 skip |
| `tests/e2e/test_agent_smoke.py` | Agent 真实链路：闲聊不调工具 / 知识库问题触发 knowledge_search（校准 DeepSeek function calling 格式） | 需 .env 双 Key，无 Key 自动 skip |

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
- 监控事件默认保留 30 天（`monitor.py` 的 `_RETENTION_DAYS`，宏观/行业序列豁免），公告增量窗口最长回补 7 天，宏观/行业增量回看 90 天
- akshare 接口变动频繁：改采集器前先跑 `scripts/probe_collectors.py` 对真实接口验证列名
- 联网搜索需在 `.env` 加 `TAVILY_API_KEY`（tavily.com 免费额度）；缺失不阻断启动，Agent 自动降级为纯知识库检索
