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

---

# 变更记录（原 CHANGELOG.md 内容并入）

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
