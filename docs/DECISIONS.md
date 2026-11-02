# 项目决策日志

> 记录所有影响项目方向的决策与显著变更：背景、选项、结论、理由。新条目追加在末尾，**只增不改**（推翻旧决策时新增条目并注明取代关系）。
> 决策记「D 编号」节，工程变更记「变更记录」节（原 CHANGELOG.md 已并入，2026-10-30 起**本项目不再单独维护 CHANGELOG**）。
> 配套文档：设计文档 `docs/plans/`。

---

## D001 · 一期技术选型（2026-10-29）

**背景**：一期 RAG 问答需确定核心框架、向量库、Embedding、前端。

**选项与结论**：
- 核心框架：LangChain+LangGraph / LlamaIndex / **自研轻量** ✅ —— 代码可控、符合 TDD 与 Pydantic 规范，三期 ReAct 自研循环
- 向量库：**Chroma** ✅（弃 Milvus：一期偏重；弃 FAISS：缺元数据过滤）—— 零部署、个人规模够用
- Embedding 服务：**阿里 DashScope text-embedding-v3** ✅（弃智谱/OpenAI）—— 中文效果好、OpenAI 兼容、成本低
- 前端：**Streamlit** ✅（弃 FastAPI+自建前端：工期翻倍；弃 Gradio：更简陋）—— 纯 Python 最快
- LLM：**DeepSeek**（用户主力密钥）

## D002 · 六期路线图确立（2026-10-29）

一期 RAG → 二期市场监控 → 三期工具调用+ReAct → 四期记忆与上下文 → 五期多 Agent 编排（五大投资思维角色）→ 六期财报解读+PTC 确定性财务计算。
反推的一期约束：pipeline.rag 是 prompt 组装唯一收口；LLM client 接口抽象；UI 与 pipeline 分离。

## D003 · 路线图 v2（2026-10-29）

用户新增二期市场监控需求（持仓公告/新闻舆情/宏观/美联储/重大会议/行业指标 + 前端双页导航），原二至五期顺延为三至六期。设计文档同步修订。

## D004 · 一期执行方式（2026-10-29）

用户选定**子 Agent 驱动**：每任务派实现 Agent → 规格+质量双审查 → 问题修复 → 下一任务；最后整体终审。
实际效果良好：审查抓出 cosine 度量空间、ids 冲突覆盖、路径穿越、retry 吞异常等 Critical/Important 问题。后续工程沿用此模式。

## D005 · 运行时修复决策（2026-10-29）

- `app/ui/app.py` → **`webapp.py`**：Streamlit 会把脚本目录插到 sys.path 最前，与包名同名会遮蔽 `app` 包；并加项目根路径自举。**此文件名不可改回**
- **闲聊分流**：打招呼/感谢/告别完整正则匹配时跳过检索直接回复（治标）；三期 ReAct 的 Agent 自主决策将取代此规则

## D006 · 版本管理与远程（2026-10-30）

- 一期完成打 **v0.1.0** 标签
- GitHub 公开仓库：https://github.com/jonathanxupeilu/DeepFinResearch（用户主动要求公开）
- 推送走 **SSH over 443**（`ssh.github.com:443`）：本机代理拦 github.com 的 HTTPS CONNECT（502）但放行 api.github.com 与 SSH
- Gitee 为规范主平台，暂未配置（用户未提供仓库地址）

## D007 · 二期 backlog 处置（2026-10-30）

一期遗留 3 个 Minor 全部清理：embedding 截断按官方 8192 token 修正为 12000 字符；citations 只保留实际标注 [n] 的引用（越界忽略/无标注保留全部）；webapp 层 st.cache_resource 缓存 pipeline（factory 保持框架无关）。

## D008 · 二期市场监控选型（2026-10-30）

| 决策点 | 结论 | 弃选与理由 |
|---|---|---|
| 数据源 | **akshare 为主，Tavily 二批补舆情** | 纯 akshare（舆情缺位）；Tavily 全覆盖（收费且额度紧张） |
| 调度 | **纯手动触发**（面板「立即采集」按钮） | Windows 任务计划（用户不要后台自动化）；APScheduler（常驻进程运维负担） |
| LLM 加工 | **无**，只存原文按来源分类 | 自动打标+摘要（用户暂不需要，留后续迭代） |
| 范围 | **核心 6 维度**先行 | 8 维度一步到位（工期长调试面大） |

关键约束：WorkBuddy 会话 connector（neodata/通达信）是会话工具，项目代码不可调用；akshare 版本钉死。
设计文档：`docs/plans/2026-10-30-market-monitor-design.md`

## D009 · 决策日志制度（2026-10-30）

建立本日志：所有影响方向/架构/范围的决策单独记录于 `docs/DECISIONS.md`，只增不改，便于后续梳理项目思路。工程执行类细节仍在设计文档中。
（2026-10-30 补充：应用户要求，当日创建的 CHANGELOG.md 并入本文件「变更记录」节，后续变更直接记于此。）

## D010 · 采集提速四件套与知识库概览卡片（2026-10-30）

「立即采集」实测约 2 分钟，根因：六源串行、公告固定回溯 7 天逐日全市场拉取、财联社接口在本机网络持续挂起吃满 60s 超时。采纳 AI 建议四点全做：

1. **并行采集**：`MonitorRunner` 线程池并发跑六源（网络 IO 密集），入库/水位线在主线程串行；返回值保持注入顺序，`on_report` 回调完成即报（供 UI 实时进度）。
2. **公告增量**：`collect_state` 表记录每维度上次成功采集水位线；公告窗口 = 距今天数+1，夹在 [1,7]，首次仍 7 天全量；采集成功的维度才推进水位线。
3. **分级超时**：新闻维度（财联社）单独 20s，其余保持 60s。
4. **过时自动清理**：采集完成后自动删除 `collected_at` 超 30 天的事件（`purge_before`），UI 显示清理条数。

另：投研顾问页新增「RAG 离线仓库概览」卡片（存量文章数/分类分布/最新入库），切片元数据增加 `indexed_at` 入库时间戳（存量数据缺该字段由统计层兜底）；分类规则：`monitor/` 前缀→市场监控、目录前缀、纯文件名→上传文档。后续若做 vault 目录级入库，可用目录名作分类。

预期采集耗时 2 分钟 → 约 20-30 秒（≈ 最慢单源）。

## D011 · 每日要闻换东财主源 + 全维度事件来源链接（2026-11-02）

D010 的分级超时只缓解了财联社挂起（20s 降级为空），未根治：每日要闻仍恒 0。探针实测三源后决策：

1. **换主源**：财联社 `stock_info_global_cls` 弃用（本机网络持续挂起）；东财 `stock_info_global_em` 为主源（实测 200 条、自带单条原文 URL）；新浪 `stock_info_global_sina` 作 fallback（20 条、无链接，em 空/失败时降级）。20s 收紧超时保留，防新闻源网络波动。
2. **全维度来源链接**：`MonitorEvent.url` 必填参考链接，UI 统一「来源链接」。有单条链接的维度（公告/要闻）用原文 URL；无单条链接的维度（宏观/美联储/行业/会议）填官方数据源页（统计局/央行/美联储/上金所/波罗的海/政府网）。

思路：选东财一举解决「恒 0」与「无链接」两问题；fallback 保鲁棒；官方源页链接让用户可溯源数据出处。设计细节见设计文档 §5「事件来源链接」与 §11-6。

## D012 · 指标类改折线图 + 存量重复清理 + 美联储正文补全（2026-11-02）

用户手动测试反馈三问题，逐一决策：

1. **指标类（宏观/行业）移出维度筛选，主页面折线图展示**：这两维度本质是时间序列而非事件，混在事件列表里既刷屏又不可比。决策：采集器改为拉近 10 年全量历史（`_MAX_HISTORY_YEARS=10`），`MonitorEvent` 增加 `value: float|None`，events 表加 `value REAL` 列（`ALTER TABLE` 迁移兼容旧库）；UI 主页面新增「📈 指标趋势」区（`st.line_chart` + 近1/3/5/10年期间选择），维度筛选与计数卡片只保留 4 个事件类维度。
2. **重大会议重复内容**：根因是 D011 给事件补 url 后 content_hash 变化，存量 url='' 旧行与新行并存。决策：**不改 hash 算法**（改了会让全部存量 hash 失效、引发大规模重复），新增 `purge_empty_url()` 在采集后清理存量无链接旧行，一次性收敛。
3. **美联储事件「没头没尾」**：原正文只有事件名+地区。决策：正文拼装 公布/预期/前值/重要性 四字段（缺失跳过），并统一附美联储官网参考链接。

设计细节见设计文档 §11-7。

## D013 · 指标采集增量化与序列保留策略（2026-11-02）

D012 的折线图上线后用户追加两点：指标应页面默认展示、「立即采集」只做增量。决策：

1. **增量采集**：宏观/行业 `collect(since)` 生效——cutoff = max(10 年前, since-90 天)，只产出回看窗口内新数据点（90 天覆盖月度数据发布滞后与修订，窗口重叠由 content_hash 去重兜底）；首次（since=None）仍全量近 10 年。akshare 接口本身返回全量历史无法服务端裁剪，增量体现在入库行数而非请求量。
2. **序列保留豁免**：30 天过时清理按 `collected_at` 会误删旧序列点（采集时间老化），`purge_before` 增加 `exclude` 参数，指标类维度长期保留；序列长度由采集端 10 年上限控制。
3. **排版**：趋势区上移页面顶部默认展示（进页面即见，不依赖采集动作），双列网格 + 每图「最新值（日期）」标注，期间选择器与标题同行。

另修复 industry 采集器未走基类 `_fetch_or_none` 的超时保护缺口。设计细节见设计文档 §11-8。

## D014 · 三期 ReAct 采用原生 function calling + AgentPipeline 并存（2026-11-02）

三期实施的关键取舍（设计文档 `docs/plans/2026-11-02-agent-react-design.md`）：

1. **原生 function calling 而非文本协议 ReAct**：DeepSeek 官方支持 `tools` 参数（e2e 实测通过），JSON 结构化远比解析 "Action:/Observation:" 文本鲁棒；"思考"过程由决策轨迹（工具调用序列）显式呈现，不要求 LLM 输出 Thought 文本。
2. **AgentPipeline 新增而非改写 RAGPipeline**：单轮 RAG 是 Agent 的退化形态且有独立价值（快、省 token、e2e 基线）；一期"rag.py 唯一收口"约束升级为"**pipeline 包**唯一收口"（rag.py 单轮 + agent.py 循环，prompts/citations 共享）。
3. **证据编号全局分配**：跨工具跨轮次统一 [n] 由循环层分配（工具返回未编号 Evidence），保证终答引用与 citations 一一对应；闲聊正则分流在 Agent 入口废除（LLM 自主决定不调工具），rag.py 通道保留。
4. **Tavily 无 Key 静默降级**：`tavily_api_key` 默认空，factory 只在有 Key 时注册 web_search，Agent 能力随配置伸缩、不阻断启动。工具层异常一律降级为失败观察文本，循环不崩。
5. **熔断**：`agent_max_iterations=5`，耗尽后最后一轮不给工具强制终答。

## D015 · Agent 时间锚定与「先事实后原因」（2026-11-02）

三期上线后用户实测：问「A股黄金板块最近波动为什么这么大」，回答泛泛而谈——无时间区间、未说明涨跌方向。根因是 LLM 无当前日期概念（「最近」解析不了）且提示词未要求先定位事实。决策：

1. **动态日期注入**：系统提示词末尾运行时追加「今天是 YYYY-MM-DD（北京时间，星期X）」（UTC+8 计算，不依赖系统时区库）；AGENT_SYSTEM_PROMPT 保持静态常量，五期角色 prompt 自动获得时间锚点。
2. **先事实后原因**：提示词规则——含时间词的问题第一轮必须先查证具体事实（区间/方向/幅度/关键事件）再分析原因；行情类回答先给事实概要。
3. **搜索带时间**：联网 query 必须带明确时间词；web_search 暴露 Tavily `time_range`（day/week/month/year，非法值忽略，真实调用验证通过）。

设计细节见三期设计文档 §11。

## D016 · 时间获取改为 current_time 工具（取代 D015-1 的写死注入，2026-11-02）

用户反馈：不应把当前日期写死注入系统消息，应让 Agent 自主判断是否调用「获取当前时间」工具。决策：

1. **新增 `current_time` 工具**（无参数，返回北京时间 + 星期；UTC+8 偏移计算，注入时钟返回 UTC、换算归工具）；factory 无条件注册（与 knowledge_search 并列必选）。
2. **撤销系统消息动态日期行**：`_system_message()` 移除，系统提示词回到静态常量——与「工具能力由注册表声明、LLM 自主决策调用」的三期架构原则一致；写死注入会让不需要时间的对话也背上日期噪音，且五期角色 prompt 复用更干净。
3. **提示词规则改写**：明确告知 LLM「你没有当前时间的概念」，含时间词的问题必须先调 current_time，再按其结果构造带时间词的搜索 query。

D015 的第 2（先事实后原因）、3（time_range）条继续有效。设计细节见三期设计文档 §12。

---

# 变更记录（原 CHANGELOG.md 内容并入）

## [Unreleased]（2026-11-02 · 三期修订三：prompt 全量收口 prompts.py）

### Changed
- **工具描述文案迁移**：knowledge_search/web_search/current_time 的
  description 与参数描述（LLM 决策依据，本质是 prompt）从各工具文件迁入
  `app/pipeline/prompts.py` 常量——手动调优任何 prompt 只改一个文件
- 当日踩坑与「时间锚定三步演进」优化逻辑记录于三期设计文档 §13

## [Unreleased]（2026-11-02 · 三期修订二：current_time 工具化）

### Added
- **current_time 工具**：无参数，返回北京时间+星期（UTC 注入时钟、+8 换算归工具）；
  factory 无条件注册；advisor 轨迹标签「🕐 当前时间」（`app/tools/current_time.py`）
- 测试：固定时钟/默认时钟/spec 形状 3 例 + factory 注册表断言更新（213 通过）

### Changed
- **撤销系统消息动态日期行**（D015-1 → D016）：agent.py 系统消息回到静态
  AGENT_SYSTEM_PROMPT；提示词规则改为「无时间概念，时间词问题必须先调 current_time」

## [Unreleased]（2026-11-02 · 三期修订：Agent 时间锚定与先事实后原因）

### Changed
- **系统提示词动态日期行**：`_system_message()` 追加「今天是 YYYY-MM-DD（北京时间，
  星期X）」，「最近/近期」有了解析基准（`app/pipeline/agent.py`）
- **AGENT_SYSTEM_PROMPT 规则 6→9 条**：时间词问题先查证事实（区间/方向/幅度）
  再析因；联网 query 必带时间词；行情回答先事实概要（`app/pipeline/prompts.py`）
- **web_search 暴露 time_range**：day/week/month/year 透传 Tavily，非法值忽略
  （`app/tools/web_search.py`）

### Added
- 测试：系统消息日期行断言、time_range 透传/缺省/枚举 3 例（210 通过）；
  Tavily time_range 真实调用验证

## [Unreleased]（2026-11-02 · 三期：工具调用 + ReAct 自主决策）

### Added
- **工具层** `app/tools/`：Tool Protocol/ToolSpec/ToolResult/Evidence 基座 +
  ToolRegistry（重名拒绝、openai_tools() 描述输出）；knowledge_search（包装一期
  Retriever）、web_search（Tavily REST，httpx，异常降级、空 Key 拒构造）
- **LLM function calling**：`chat_with_tools` + ToolCall/ChatResponse（Pydantic），
  参数非法 JSON 降级空参，沿用 tenacity 重试（`app/llm/client.py`）
- **AgentPipeline**（`app/pipeline/agent.py`）：ReAct 循环、全局证据编号 [n]、
  未知工具/工具失败容错、max_iterations 熔断后强制终答；AGENT_SYSTEM_PROMPT
- **决策轨迹**：`TraceStep` 模型 + `RagAnswer.trace`；advisor 页「🧠 决策轨迹」
  expander + URL 引用渲染为链接；CLI 轨迹逐行打印
- **共享引用构建** `app/pipeline/citations.py`（rag/agent 共用）；
  `build_agent_pipeline()` factory 入口；config 新增 tavily_api_key /
  agent_max_iterations / tavily_max_results；pyproject 显式声明 httpx
- 测试：工具层/LLM 映射/Agent 循环 6 场景/factory 降级注册/advisor AppTest/
  CLI 轨迹（unit+integration 207 通过）+ e2e 真实 DeepSeek 冒烟 2 例

### Changed
- **advisor 页与 CLI 入口切换到 AgentPipeline**：投研顾问由单轮 RAG 升级为
  自主工具决策；RAGPipeline 保留为单轮快速通道（e2e 基线不动）
- Agent 入口废除闲聊正则分流（D005 治标方案退役，LLM 自主决定不调工具）

## [Unreleased]（2026-11-02 · 市场监控：指标排版优化与采集增量化）

### Changed
- **指标排版优化**：趋势区上移至页面顶部默认展示，双列网格布局，期间选择器与
  标题同行，每图标注「最新值（日期）」（`app/ui/pages/monitor.py`）
- **指标采集增量化**：宏观/行业尊重 since 水位线，只采水位线回看 90 天内的新
  数据点（首次仍全量 10 年）；`purge_before` 增加 exclude 参数，指标类退出
  30 天过时清理防历史序列丢失；industry 改走 `_fetch_or_none` 对齐超时保护

### Added
- 测试：macro/industry 增量 since 过滤用例、purge_before exclude 豁免用例（163 通过）

## [Unreleased]（2026-11-02 · 市场监控：指标折线图 / 重复清理 / 美联储正文）

### Added
- **指标趋势折线图**：宏观/行业采集器改拉近 10 年历史序列（PMI/CPI/社融、
  黄金/BDI），`MonitorEvent.value` + events 表 `value REAL` 列（ALTER 迁移）；
  主页面「📈 指标趋势」区按指标分图，配近 1/3/5/10 年期间选择
  （`app/monitor/collectors/macro.py`、`industry.py`、`app/ui/pages/monitor.py`）
- **存量重复清理**：`EventStore.purge_empty_url()` 删除 url='' 的旧行
  （D011 补链接后 hash 变化导致新旧并存），采集后自动执行并在 UI 显示条数

### Changed
- **宏观/行业移出维度筛选**：筛选下拉与计数卡片只保留公告/要闻/美联储/会议
  4 个事件类维度，指标类以图表形态常驻主页面
- **美联储正文补全**：content 拼装 地区+公布/预期/前值/重要性（缺失字段跳过），
  统一附美联储官网参考链接（`app/monitor/collectors/fed.py`）

## [Unreleased]（2026-11-02 · 市场监控：新闻源切换与全维度来源链接）

### Changed
- **每日要闻主源切换**：财联社 `stock_info_global_cls` 在部分网络下持续挂起
  （20s 超时降级为空，致该维度恒为 0），主源改用东方财富 `stock_info_global_em`
  （200 条、自带单条原文链接），空/失败降级新浪 `stock_info_global_sina`
  （`app/monitor/collectors/news.py`）
- **全维度事件附来源链接**：宏观→统计局/央行、美联储→fed 官网、行业→上金所/波罗的海
  交易所、重大会议→政府网、要闻→单条原文/新浪首页；UI 链接文案统一为「来源链接」

### Fixed
- 既有门禁欠账清理：runner.py 无用 noqa、probe 脚本多余 utf-8 声明、6 个文件按
  black 26.x 新规则重排（此前全量 `black --check .` 未跑过）

## [Unreleased]（2026-11-02 · 投研顾问页概览卡片同步修复）

### Fixed
- **入库后概览卡片实时同步**：`advisor.py` 将 `_show_library_card()` 渲染移至入库处理之后，
  使「存量文章/切片总数/分类/最新入库」在入库成功的同一次 rerun 内刷新，无需再次交互
  （此前卡片先于入库渲染读到旧数据，要等下次交互才更新）

## [Unreleased]（2026-10-30 · 二期优化：采集提速与知识库概览）

### Added
- 投研顾问页「RAG 离线仓库概览」卡片：存量文章数（按 source 去重）、分类分布、
  最新入库短标题（`app/retrieval/stats.py` 纯函数统计 + `indexed_at` 元数据）
- 事件过时自动清理：采集后删除超 30 天旧事件，UI 显示清理条数
- 每维度采集水位线：`collect_state` 表，公告按增量窗口回补

### Changed
- 六源采集由串行改线程池并行，单源完成即回调（UI `st.status` 实时进度）
- 新闻维度独立 20s 超时（财联社接口挂起不再拖慢整体）

## [Unreleased]（2026-10-30 · 二期市场监控）

### Added
- **市场监控 6 维度采集**：持仓公告/每日要闻/宏观指标/美联储/重大会议/行业指标，
  akshare 数据源，面板「立即采集」手动触发，单源失败隔离（`app/monitor/`）
- **SQLite 事件存储**：`data/monitor.db`，内容 hash 去重，按维度/时间筛选
  （`app/monitor/store.py`）
- **双页导航**：`st.navigation` 拆分「投研顾问」与「市场监控」，聊天页迁移
  `app/ui/pages/advisor.py`（入口命令不变）
- **事件入库知识库联动**：监控事件一键转 Document 走一期 Indexer，投研顾问可检索引用
- **持仓配置**：`config/holdings.json` 驱动持仓公告维度（缺失时该维度无数据不报错）

### Changed
- **akshare 列入依赖**：`pyproject.toml` 补录 `akshare>=1.16`（此前仅环境安装未声明，
  重建环境会缺包）

### 实施中偏差（相对计划/D008）
- **AkshareCollector 基类抽取**：收敛各 akshare 采集器重复的取数/容错逻辑
- **持仓公告多日窗口**：近 7 日逐日拉取公告，替代单日查询
- **重大会议日历数据修正**：`config/policy_calendar.json` 按公开惯例修正会议日期
  （如中央经济工作会议通常 12 月举行）

## [Unreleased]（2026-10-30 · 二期 backlog 清理）

### Fixed
- **embedding 截断保护**：截断上限由 6000 字符修正为 12000 字符，依据官方
  text-embedding-v3 单条 8192 token 限制（中文 ~1.5 字符/token 保守换算）（`app/llm/embedding.py`）

### Added
- **引用精确解析**：回答中实际标注 `[n]` 才保留对应引用来源；越界编号忽略；
  无任何标注时保留全部来源不丢信息（`app/pipeline/rag.py`）

### Changed
- **Streamlit pipeline 缓存**：`webapp.py` 用 `st.cache_resource` 会话间复用
  pipeline；`factory.py` 保持框架无关以继续服务 CLI 与测试

## [v0.1.0] - 2026-10-29

一期：本地 RAG 问答助手完整交付（13 个 TDD 任务，子 Agent 驱动 + 每任务规格/质量双审查 + 整体终审）。

### Added
- 文档入库：md/txt/pdf/docx 加载 → 段落聚合切片（可配 chunk_size/overlap）→
  DashScope text-embedding-v3 向量化（分批/重试/截断保护）→ Chroma 持久化（cosine 空间）
- 入库去重：内容 hash 相同跳过；文档更新自动删旧重建；ids 含 source 防跨文档覆盖
- 检索：top-k + 余弦相似度阈值过滤，空结果诚实拒答（不硬答）
- 生成：prompt 组装唯一收口于 pipeline，system prompt 强约束"仅依据上下文"，
  角色化 system prompt 可注入（为五期多 Agent 预留）
- 双入口：Streamlit 网页版（聊天 + 知识库管理）与 CLI REPL，均带引用展示
- 闲聊分流：打招呼/感谢/告别完整匹配时跳过检索直接回复
- 配置：Pydantic Settings + `.env`（DeepSeek + DashScope 双 Key）
- 测试体系：unit/integration/e2e 三层；mock 隔离、真实 API 冒烟、无 Key 自动 skip

### Fixed
- Chroma collection 显式指定 cosine 度量空间（默认 l2 会致相似度换算错误）
- 上传文件名路径穿越防护（剥离目录成分）
- tenacity 重试限定可恢复异常（限流/连接）+ `reraise=True` 保留真实根因
- Streamlit 运行时 `app` 包遮蔽（`app.py` 改名 `webapp.py` + 项目根路径自举）
- CLI REPL 运行时容错（API 异常不杀会话）+ 缺 Key 友好提示

### Quality
- 61 unit/integration 测试 + e2e 真实 API 冒烟全绿
- ruff / black / mypy 零错误
