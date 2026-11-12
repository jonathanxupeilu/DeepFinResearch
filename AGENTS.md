# AGENTS.md — DeepFinResearch 项目索引

> 面向 AI Agent / 新成员的项目导航。全局开发规范（编码/TDD/质量门禁/密钥管理）见 `~/.qoder-cn/agents.md`，本文件只做**项目级索引**：改哪个文件前，先在这里找到它是什么、归哪期管、对应哪份文档。

## 项目是什么

本地知识库 RAG 投研问答助手，七期路线图演进为多 Agent 投研平台。当前状态：**一至四期已完成，五至七期未启动**（最后代码提交 2026-11-12）。四期三层评估器（代码 / LLM judge / 人工审批）全部落地；2026-11-12 实测 ruff/black/mypy 零错误、全量 pytest 306 passed，e2e 冒烟含真实 function calling 链路。**状态快照时效**：`common_questions` 10/10 与网页端签字「BC-10 pass / BC-11 fail」均为 11-06 **D024 修复前**结果；修复后 BC-11 曾在联网路径翻车，规则 13 已加固并在 6 次采样（5 次覆盖联网）中验证通过（D025）。2026-11-12 已闭环：10 个提交 push、云端 BC-11 契约同步为 4 条 `must_not`、红队探针接入门禁（D026）。遗留：BC-01 灰区与 D025 新灰区待人工签定。

## 架构总览（big picture）

### 目录地图

```
DeepFinResearch/
├── app/                        # 应用代码（明细见「代码索引」）
│   ├── factory.py              # 组合根：唯一依赖组装入口
│   ├── pipeline/               # prompt 收口 + RAG / Agent 问答链路
│   ├── tools/ llm/ retrieval/  # 适配层：工具注册表 / 大模型 / 向量库
│   ├── ingest/ monitor/ evals/ # 文档入库 / 市场监控 / 评估器
│   ├── ui/ cli.py              # Streamlit 双页 + 终端 REPL（薄壳）
│   └── config.py models.py chat_store.py
├── tests/                      # unit / integration / e2e（见「测试索引」）
├── scripts/                    # 采集探针 + Evals 构建 / 推送 / 运行
├── evals/                      # *.yaml 真源 + results/（产物，已 gitignore）
├── docs/                       # plans/ 分期设计与实施计划 + DECISIONS.md
├── config/                     # holdings.json / policy_calendar.json（运行期配置）
├── data/ knowledge/            # 已 gitignore：chroma+monitor.db / 用户文档
└── pyproject.toml uv.lock .env.example
```

一次提问的主链路（跨文件，详见「核心链路」）：`ui/cli → factory（组装）→ pipeline/agent.py（ReAct）→ tools/ → llm/client.py`；`pipeline/` 统一装配 prompt，引用经 `citations.py` 按 `[n]` 回挂。

### 架构不变量（跨文件约束）

- **组合根唯一**：所有组件只在 `app/factory.py` 接线，UI/CLI 共用；新增工具 = 一个类 + factory 注册一行。
- **prompt 单一真源**：全部提示词只在 `app/pipeline/prompts.yaml`，`pipeline/` 包是组装收口；调优话术不改 Python。
- **禁裸 dict**：核心业务数据一律 Pydantic v2（`app/models.py`），跨层传递用模型不用 dict。
- **检索空间**：Chroma 集合必须 cosine（`metadata={"hnsw:space": "cosine"}`），retriever 相似度阈值才有意义。
- **降级不抛**：工具内部 / 采集器 / 空检索均 catch 异常降级为文本或空结果，链路不中断。
- **观测与判分隔离**：LLM judge 用不带 `wrap_openai` 的原生客户端，避免污染实验 trace。

## 路线图（v3，七期）

| 期 | 内容 | 状态 |
|---|---|---|
| 一期 | 本地 RAG 问答（入库→检索→prompt→LLM 带引用）+ Streamlit/CLI | ✅ 完成 |
| 二期 | 市场监控面板（公告/要闻/宏观/美联储/会议/行业 6 维度），左菜单双页导航 | ✅ 完成 |
| 三期 | 工具调用 + ReAct 自主决策（AgentPipeline，取代一期闲聊正则分流） | ✅ 完成 |
| 四期 | 测评集与评估体系 Evals（LangSmith 观测 + 基线集 + 坏案例集 + 代码/LLM/人工三层评估器） | ✅ 完成：三层评估器 + 网页端人工审批签字（D020-D024）。注意 10/10 全量回归是 D024 修复前产物；BC-11 修复后仅单条定向回归且未走联网路径，稳定性见 D025 |
| 五期 | 记忆与上下文管理（短期/长期，ContextBuilder） | 未启动 |
| 六期 | 多 Agent 编排（芒格/施洛斯/巴菲特/邓普顿/马克斯五种投资思维角色） | 未启动 |
| 七期 | 财报/研报深度解读 + PTC 确定性财务计算（DCF/清算价值） | 未启动 |

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/plans/2026-10-29-local-rag-qa-design.md` | 总设计：一期架构 + 二至七期展望。动架构/规划新期时读 |
| `docs/plans/2026-10-29-local-rag-qa-phase1.md` | 一期实施计划：13 个 TDD 任务全文。改一期代码前对照 |
| `docs/plans/2026-10-30-market-monitor-design.md` | 二期设计（§11 为实施修订记录）。改 monitor 前读 |
| `docs/plans/2026-10-30-market-monitor-phase2.md` | 二期实施计划：10 个 TDD 任务全文 |
| `docs/plans/2026-11-02-agent-react-design.md` | 三期设计（§10 决策摘要）。改 agent/tools/llm client 前读 |
| `docs/plans/2026-11-02-agent-react-phase3.md` | 三期实施计划：9 个 TDD 任务全文 |
| `docs/plans/2026-11-04-evals-observability-litefuse-feasibility.md` | 四期观测平台选型调研（定案见 §10 / D019）+ **§11 实施落地附记**（评估体系实际交付与偏差）。改 `evals/` 或 judge 口径前读 |
| `docs/DECISIONS.md` | **决策日志**（D001-D024，只增不改）+ **踩坑记录**（唯一记录处）+ 变更记录。改动前先查、做完回写；四期关键决策：D020 行为契约 / D021 三层评估器 / D022 judge 观测 / D023 闲聊约束落 prompt / D024 人工审批闭环与 BC-11 合规红线 |
| `README.md` | 快速开始：安装、配置 .env、启动命令 |
| `config/holdings.json` | 持仓 A 股代码（JSON 数组，`code` 为 6 位代码），驱动公告采集维度；缺文件则该维度无数据、其余维度不受影响 |
| `config/policy_calendar.json` | 重大会议（POLICY 维度）日历，`PolicyCollector` 读取并取未来 30 天内的临近会议，坏条目逐条跳过 |

## 代码索引

### 入口（改前先懂 factory）

| 文件 | 职责 |
|---|---|
| `app/factory.py` | **依赖组装唯一入口**：build_pipeline / build_agent_pipeline / build_ingest_components / build_monitor_store / build_monitor_runner。所有组件在此接线，UI/CLI 共用 |
| `app/ui/webapp.py` | Streamlit 入口壳：`st.navigation` 双页（每页显式 url_path）+ 隐藏别名页保住 /advisor 直达路由。⚠️ 不能叫 app.py（遮蔽 app 包）、页面目录必须叫 `views/` 不能叫 `pages/`（pages/ 是魔法目录，冷启动直达 URL 会落到空白页） |
| `app/ui/views/advisor.py` | 【投研顾问】Agent 聊天（决策轨迹 expander + URL 引用链接）+ 右上「历史对话」折叠面板 + 侧边栏上传入库 + 离线仓库概览卡片 |
| `app/ui/views/monitor.py` | 【市场监控】左侧「指标分类」单选 → 右侧「📈 指标趋势」折线图（同指标同比/环比/增量卡内切换、双列、近1/3/5/10年）/ 立即采集 / 事件列表（公告/要闻/美联储/会议 4 维度）/ 一键入库 |
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
| `app/pipeline/agent.py` | AgentPipeline：function calling ReAct 循环、全局证据编号 [n]、未知工具/失败容错、max_iterations 熔断后强制终答；`answer(question, history, session_id)` 注入多轮上下文（最近 10 条、单条截断 1500 字）；四期观测：`@traceable` 埋 answer（内部 `_traced_answer` 接 langsmith_extra）与工具执行 span，session_id 经 metadata 串 LangSmith thread | 与 rag.py 并列为 prompt 收口；系统提示词静态常量（时间靠 current_time 工具，D016）；六期多 Agent 在此注入角色 |
| `app/pipeline/rag.py` | 检索→prompt→LLM→RagAnswer 带引用；空检索诚实拒答；四期观测：`@traceable` 埋 answer 与检索 span | 单轮快速通道（e2e 基线），Agent 入口已废除闲聊正则 |
| `app/pipeline/prompts.yaml` | **全部 prompt 唯一维护处**：rag/agent/tools 三组提示词（SYSTEM_PROMPT / AGENT_SYSTEM_PROMPT / USER_TEMPLATE / 拒答文案 / 工具 description）；agent 规则 2 含纯闲聊「一句话 20 字内」约束（D023 修 BC-06），规则 13 为合规红线「外部研报目标价也不得复述」（D024 修 BC-11） | 调优任何话术只改此文件；改规则 2 必须跑 `run_eval.py --only BC-06,BC-12`，改规则 13 必须跑 `--only BC-11` **+ `probe_bc11_redteam.py --repetitions 3`**（门禁，见运行须知）；两条都是软约束，回归才作数 |
| `app/pipeline/prompts.py` | prompts.yaml 加载器：读 yaml 暴露同名常量；闲聊正则 + `is_smalltalk`（程序逻辑）保留在此 | 与 rag.py/agent.py 并列为 prompt 收口 |
| `app/pipeline/citations.py` | 引用构建共享逻辑（按 [n] 标注过滤/越界忽略/无标注保留全部） | rag 与 agent 共用 |
| `app/tools/base.py` | Tool Protocol + ToolSpec/ToolResult/Evidence（Pydantic） | 工具内部 catch 全部异常降级失败文本；Evidence 不编号，编号归循环层 |
| `app/tools/registry.py` | ToolRegistry：注册（重名拒绝）/get/openai_tools() | 新工具 = 一个类 + factory 注册一行 |
| `app/tools/knowledge_search.py` | 包装一期 Retriever 的知识库检索工具 | query 必填，检索空/异常均降级观察文本 |
| `app/tools/current_time.py` | 当前北京时间+星期（无参数），Agent 自主调用锚定「最近」 | 注入时钟返回 UTC，+8 换算归工具；factory 无条件注册 |
| `app/tools/web_search.py` | Tavily REST 联网搜索（httpx，Bearer 鉴权，15s 超时） | 空 Key 构造即拒绝；factory 只在有 Key 时注册 |
| `app/retrieval/retriever.py` | top-k 检索 + cosine 相似度阈值过滤 | collection 必须是 cosine 空间 |
| `app/retrieval/store.py` | Chroma 封装（upsert/query/delete/按 source 管理/get_all_metadatas） | 创建集合须带 `metadata={"hnsw:space": "cosine"}` |
| `app/retrieval/stats.py` | 离线仓库统计（纯函数）：文章数/分类/最新入库 | 只聚合不查库；缺 indexed_at 的旧数据兜底 |
| `app/llm/client.py` | LLMClient Protocol + DeepSeekClient：chat / chat_with_tools；四期观测：`wrap_openai` 包装 + 构造时按 langsmith_api_key 注入 LANGSMITH_* env | 走接口抽象；工具参数非法 JSON 降级空参；重试仅限限流/连接类；无 LangSmith Key 时 wrap_openai 完全透传 |
| `app/llm/embedding.py` | DashScope embedding（分批 10 条/重试/截断） | 重试仅限 RateLimitError/APIConnectionError + reraise=True |

### 入库链路（上传文档的数据流）

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/ingest/loaders.py` | md/txt/pdf/docx → 纯文本 | 七期财报表格解析在此替换/扩展 |
| `app/ingest/splitter.py` | 段落聚合切片 + 超长硬切带 overlap | 参数校验拦截非正值 |
| `app/ingest/indexer.py` | hash 去重 + 版本替换 + 切片入库 | ids 必须含 source；元数据带 indexed_at（统计卡片依赖） |

### 市场监控（二期）

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `app/monitor/models.py` | Dimension 六值枚举 / MonitorEvent（含 `value` 指标数值）/ CollectReport | 新维度先扩枚举；事件类 value=None |
| `app/monitor/store.py` | SQLite：events 表（hash 去重、value 列 ALTER 迁移）+ collect_state 水位线 + purge_before 过时清理（exclude 豁免指标类）+ purge_empty_url 存量清理 | 水位线只在采集成功后推进；改 hash 算法会使存量失效，禁止 |
| `app/monitor/collectors/base.py` | Collector Protocol（`collect(since=...)`）+ AkshareCollector 基类（超时保护/日期解析） | 超时默认 60s；naive 时间按北京时间转 UTC |
| `app/monitor/collectors/*.py` | 6 个采集器：公告增量窗口；新闻东财主源+新浪 fallback（20s 独立超时）；宏观 9 序列（PMI/CPI/M2 同比环比、GDP 同比+环比自算、社融增量+同比自算）、行业黄金/BDI，首次拉近10年、此后按水位线回看90天；美联储正文含公布/预期/前值/重要性；全维度带来源链接 | 单源异常降级空结果，不抛出 |
| `app/monitor/runner.py` | 线程池并行执行，on_report 完成即报，返回保持注入顺序 | 入库/水位线在主线程 |
| `scripts/probe_collectors.py` | 真实接口采集探针（冒烟/排查列名用） | 直连 akshare，会联网 |

### 四期 Evals（观测 / 基线集 / 坏案例 / 评估器）

> 云端真源：`common_questions`（10 条坏案例 = 用户手录 6 + 脚本推 4）与 `deepfin-evals-v1`（6 题正常基线），均在 LangSmith **APAC 端点**。本地真源是 `evals/*.yaml` 与 `app/evals/`。

| 文件 | 职责 | 关键约束 |
|---|---|---|
| `evals/questions.yaml` | 正常题测评集**本体**（人工唯一真源）：6 题 + `expected` 判分要点 + `time_sensitive`（true 的题跨次只比指标不比答案文本） | 题目 id 改名后重跑会自动清掉 dataset 里的旧条目 |
| `evals/dataset.yaml` | **生成物**：基线答案 / 轮数 / LLM 次数 / token / 引用数 / 逐条 query / trace 链接 + git_rev 与 config 快照 | 不要手改；判分口径变了改 questions.yaml 再重跑 |
| `evals/bad_cases.yaml` | 坏案例**真源**：BC-09/10/11/12（用户复核版），outputs 写「期望行为契约」而非标准答案（D020）；BC-11 有 4 条 `must_not`，第 4 条禁联网研报目标价（D024） | 与 `common_questions` 里手录的 BC-01~06 共用 schema；`evaluators` / `time_sensitive` 只留本地；**本地 BC-11 契约领先云端**，推 `--replace` 前两边不一致 |
| `evals/judge_prompts.yaml` | judge 提示词**版本化真源**：`version: 2 + versions{1 全文, 2 全文}`，v1 原文保留供旧口径复跑 | 改判分口径必须升版本、不要覆盖旧版；experiment metadata 会记版本号 |
| `app/evals/code_evaluator.py` | 代码评估器（Pydantic 纯函数）：工具序列 / 引用要求 / 编号越界；`EvalObservation` 含工具参数与引用切片正文 | `must_not` 是自然语言，代码层一律 skip 并上报 coverage；`must_mention` 默认委派 judge（`literal_mentions=True` 为调试开关） |
| `app/evals/llm_judge.py` | LLM judge：按契约判 `expected_behavior` / `must_not` / 语义等价的 `must_mention`，输出结构化 `JudgeVerdict` | **必须用不带 `wrap_openai` 的原生客户端**，否则 judge 调用会污染实验 trace；解析失败降级 error，绝不虚报 pass |
| `app/evals/combine.py` | 双层合并口径：代码层 `cov=0`（无可判项）时只按 judge；judge 未判到不给分 | D021 修正过「cov=0 被 AND 判失败」的口径缺陷 |
| `scripts/build_evals.py` | 真实链路采集 + 推 `deepfin-evals-v1`；`--dry-run` / `--only` / `--push` / `--push-only` | 会真实调 DeepSeek/Tavily；token 与 LLM 次数按 session_id 回读，子 run 批量上报需等待 |
| `scripts/push_bad_cases.py` | 把 `bad_cases.yaml` 推 `common_questions`；默认追加且跳过已存在 case_id，`--replace` 才按 case_id 精确覆盖 | **绝不删除非本批 case_id 的 example**（用户手录的 BC-01~06）；目标 Dataset 不存在时报错退出、不自动新建 |
| `scripts/run_eval.py` | 跑 experiment：`evaluate()` + 代码层/judge 混装，明细落 `evals/results/*.jsonl` | `--only` 定向回归 / `--repetitions`（默认 1）/ `--evaluators` / `--judge-version`（旧口径复跑）/ `--from-results`（离线复算、不重花钱）/ `--dry-run` |

### 基础设施

| 文件 | 职责 |
|---|---|
| `app/config.py` | Pydantic Settings 读 .env（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY 必填；TAVILY_API_KEY 可选=空则不注册 web_search；LANGSMITH_API_KEY 可选=空则观测静默；LANGSMITH_ENDPOINT 可选=空则美国端点，APAC/EU 账号必填；agent_max_iterations 等全部可调参数） |
| `app/models.py` | Pydantic v2 模型：Document/Chunk/RetrievedChunk/Citation/TraceStep/RagAnswer（含 trace）/ChatMessage/ChatSession——**禁裸 dict 传核心业务数据** |
| `app/chat_store.py` | 历史对话存储：JSON 单文件会话持久化（同 id upsert、updated_at 倒序、原子写），advisor 页「历史对话」面板续聊数据源 |

## 测试索引

| 目录 | 覆盖 | 依赖 |
|---|---|---|
| `tests/unit/` | 一期（config/models/splitter/loaders/embedding/llm_client/rag_pipeline/factory/cli）+ 二期（monitor 模型/runner/各采集器/stats）+ 三期（citations/tool_registry/knowledge_search/web_search/agent_pipeline/advisor 页）+ 四期（bad_cases / code_evaluator / llm_judge / combine / prompts 规格守卫）；共 40 个测试文件 | 无网络、无 Key |
| `tests/integration/` | store/retriever/indexer（真实 Chroma，tmp_path）+ monitor store（真实 SQLite） | 无 Key |
| `tests/e2e/test_smoke.py` | 全链路入库→检索→问答（真实 API） | 需 .env 双 Key，无 Key 自动 skip |
| `tests/e2e/test_agent_smoke.py` | Agent 真实链路：闲聊不调工具 / 知识库问题触发 knowledge_search | 需 .env 双 Key，无 Key 自动 skip |

```bash
# 常用命令（Windows, Git Bash）；命令用 .venv/Scripts/python.exe 显式解释器，
# 激活 venv 后等价写 python / pytest（README 风格），二者一致

# ── 环境 / 安装 ──
python -m venv .venv && .venv/Scripts/activate   # 建 venv 并激活
uv pip install -e ".[dev]"                       # 装包必须用 uv（~/.local/bin/uv.exe）；venv 内 pip 走不了代理
cp .env.example .env                             # 填 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY

# ── 质量门禁 ──
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m black --check .
.venv/Scripts/python.exe -m mypy app
# 改 prompts.yaml 规则 13 时追加下方「评估实验」段的红队探针（真实链路、退出码非 0 不放行）

# ── 测试 ──
.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q              # 全量无 Key 测试（2026-11-12 实测 306 passed）
.venv/Scripts/python.exe -m pytest tests/e2e -m e2e -v                          # 真实 API 冒烟（e2e marker 见 pyproject.toml）
.venv/Scripts/python.exe -m pytest tests/unit/test_agent_pipeline.py -q         # 单个测试文件
.venv/Scripts/python.exe -m pytest tests/unit/test_agent_pipeline.py::test_name -q  # 单个用例（test_name 换成实际用例名）
.venv/Scripts/python.exe -m pytest -k "smalltalk" -q                           # 按关键字筛选用例

# ── 启动 ──
.venv/Scripts/python.exe -m streamlit run app/ui/webapp.py           # 网页版
.venv/Scripts/python.exe -m app.cli                                  # 终端版

# ── 评估实验（四期）──
.venv/Scripts/python.exe scripts/run_eval.py --dry-run                # 预览评估实验（不花钱）
.venv/Scripts/python.exe scripts/run_eval.py --only BC-06,BC-12       # 闲聊规则 2 定向回归
.venv/Scripts/python.exe scripts/run_eval.py --only BC-11             # 合规规则 13 定向回归
.venv/Scripts/python.exe scripts/probe_bc11_redteam.py --repetitions 3  # BC-11 联网路径红队探针（强制覆盖 web_search + 覆盖度门禁，D025/D026）
.venv/Scripts/python.exe scripts/run_eval.py --from-results evals/results/eval_20261106T060048Z.jsonl  # 口径修订后离线复算
.venv/Scripts/python.exe scripts/push_bad_cases.py --dry-run          # 预览坏案例推送
```

## 运行须知

- **装包必须用 uv**（`~/.local/bin/uv.exe`，清华+阿里镜像已持久化）；venv 内 pip 走不了代理
- `.env` 不入 git；`data/`（chroma 持久化 + monitor.db）、`knowledge/`（用户文档）同样不入 git
- 新增功能的任务格式参照 `2026-10-29-local-rag-qa-phase1.md`：失败测试→最小实现→提交
- 监控事件默认保留 30 天（宏观/行业序列豁免），公告增量窗口最长回补 7 天，宏观/行业增量回看 90 天
- akshare 接口变动频繁：改采集器前先跑 `scripts/probe_collectors.py` 对真实接口验证列名
- 联网搜索需在 `.env` 加 `TAVILY_API_KEY`（tavily.com 免费额度）；缺失不阻断启动，Agent 自动降级为纯知识库检索
- 四期评估：LangSmith 用 **APAC 端点**（`LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com`）；`common_questions` 含用户手录条目，任何推送脚本都不得删除非本批 case_id
- 改 judge 判分口径 → 升 `evals/judge_prompts.yaml` 版本，用 `--judge-version N` 复跑旧实验做前后对比；**v1 原文不得删**
- 改 `prompts.yaml` 的 agent 规则 2（闲聊）后必须跑 `run_eval.py --only BC-06,BC-12`：`is_smalltalk` 正则对组合问候（如「你好，谢谢啦！」）漏判，约束只能靠 prompt + eval 回归（D023）
- 改 agent 规则 13（合规红线）后必须两条都跑：`run_eval.py --only BC-11`（云端契约 2026-11-12 已同步为 4 条 `must_not`，判分项含「禁复述联网研报目标价」）+ `scripts/probe_bc11_redteam.py --repetitions 3`（本地真源、强制覆盖 `web_search` 路径）。后者退出码非 0（违规 / 判分异常 / 联网 0 覆盖）即不放行；正式回归 5 次实测联网覆盖仅 1/5，单靠它守不住（D024/D025/D026）
- `evals/results/` 是实验产物、已 gitignore；真源是 `evals/*.yaml` 与 `app/evals/`
