# DeepFinResearch 智能投研助手 — 设计文档

> 日期：2026-10-29 ｜ 项目：DeepFinResearch ｜ 状态：已确认
> 路线图 v2：新增二期「市场监控」，原二至五期顺延为三至六期

## 1. 产品愿景

DeepFinResearch 最终形态：以本地知识库为底座的智能投研助手，六期演进：

- **一期（本期）**：RAG 问答 —— 文档入库 → 向量检索 → prompt 拼接 → LLM 回复（带引用）+ Streamlit 界面
- **二期**：市场监控工具 —— 每日监控持仓股公告/新闻/舆情/宏观/行业指标 + 前端导航改造（详见 §6）
- **三期**：工具调用（联网搜索等）+ ReAct 自主决策循环（详见 §7）
- **四期**：上下文与状态管理，短期/长期记忆，Agent 具备记忆能力（详见 §8）
- **五期**：多 Agent 编排，不同投资思维角色 Agent（详见 §9）
- **六期**：财报/研报深度解读 + PTC 确定性财务计算（详见 §10）

## 2. 一期技术选型（已确认）

| 项 | 选型 | 理由 |
|---|---|---|
| 核心框架 | 自研轻量（无 LangChain） | 代码可控、符合 TDD/Pydantic 规范 |
| LLM | DeepSeek API（`DEEPSEEK_API_KEY`） | 用户主力 |
| Embedding | 阿里 DashScope text-embedding-v3（`DASHSCOPE_API_KEY`） | 中文效果好，OpenAI 兼容接口 |
| 向量库 | Chroma（本地持久化） | 零部署，个人规模够用 |
| 前端 | Streamlit | 纯 Python 出聊天界面，最快 |
| 文档格式 | md / pdf / docx | — |

## 3. 一期架构

```
knowledge/            用户文档目录 (md/pdf/docx)
    │ ①入库
    ▼
loaders → splitter → embedding(DashScope) → Chroma(data/chroma/ 持久化)
                                              │
用户提问 → Streamlit UI → rag pipeline ────────┘ ② 检索 top-k
                              │ ③拼 prompt（含来源标注）
                              ▼
                        DeepSeek API → 回复 + 引用 [1][2]
```

## 4. 目录结构

```
app/
  config.py        # Pydantic Settings 读 .env
  models.py        # Pydantic v2: Chunk, Document, Citation, RetrievedChunk
  llm/
    client.py      # DeepSeek chat（接口抽象，三期可换/加模型）
    embedding.py   # DashScope embedding（OpenAI 兼容）
  ingest/
    loaders.py     # md/pdf/docx → 纯文本
    splitter.py    # 切片（chunk_size / overlap 可配）
    indexer.py     # 切片 → embedding → Chroma 入库（hash 去重）
  retrieval/
    retriever.py   # query → top-k + 相似度阈值过滤
  pipeline/
    rag.py         # 检索 → prompt 模板 → LLM → 回复带引用（一期所有 prompt 组装收口于此）
  ui/
    app.py         # Streamlit：聊天页 + 知识库管理页
tests/
  unit/            # splitter、prompt 构建（mock LLM/embedding）
  integration/     # 真实 Chroma 本地库
  e2e/             # 冒烟：入库→检索→问答链路
data/chroma/       # 向量库持久化
knowledge/         # 用户文档
docs/plans/        # 设计与实施计划
```

## 5. 关键决策

1. **后期能力预留原则（YAGNI）**：一期只保证三点——`pipeline.rag` 是所有 prompt 组装的唯一收口；LLM client 走接口抽象；UI 页面与业务 pipeline 分离。三期 ReAct 在 pipeline 层加循环，四期插入 ContextBuilder，五期实例化多个 pipeline 配置角色 prompt，UI 与检索层不动。工具注册等一概不提前实现。
2. **Prompt 策略**：system prompt 强制「仅依据上下文回答，检索不到就明说」；回复内联标注来源 `[1][2]`，附引用列表（文档名 + 片段）。
3. **错误处理**：
   - LLM/Embedding API 调用用 tenacity 指数退避重试；
   - 检索结果为空或全部低于阈值 → 明确告知「知识库中未找到相关内容」，不硬答；
   - 入库按内容 SHA256 去重，重复文档跳过；
   - `.env` 缺必需密钥 → 启动即报错退出。
4. **测试策略（TDD）**：unit（mock LLM/embedding，测 splitter 切分边界、prompt 构建、去重逻辑）；integration（真实 Chroma：入库/检索/过滤）；e2e 冒烟（真实 API，可跳过标记 `@pytest.mark.e2e`）。

## 6. 二期工程：市场监控（已确认范围，届时出详细设计）

**目标**：每日自动监控市场信息面，前端面板展示；主界面改为左侧菜单导航——【投研顾问】进入 Agent 对话模式（一期能力），【市场监控】进入监控面板。

**监控维度**：

| 维度 | 内容示例 | 候选数据源（届时评估） |
|---|---|---|
| 持仓股公告 | 定期报告、增减持、停复牌等 | 巨潮资讯 / 交易所接口 |
| 重大新闻 & 每日要闻 | 财经要闻聚合 | Tavily / RSS / 财经媒体 API |
| 网络舆情 | 社交媒体热度、负面情绪 | 搜索 API / 舆情源 |
| 热点事件 | 主题催化、突发事件 | 聚合来源 + LLM 归类 |
| 宏观经济指标 | PMI/CPI/社融等 | neodata / akshare |
| 美联储动作 | FOMC 决议、点阵图、官员讲话 | FOMC 日历 / 新闻源 |
| 重大会议 | 中央经济工作会议、两会、政治局会议 | 政策日历（手工+新闻触发） |
| 行业监控指标 | 库存、金价、运价、动销等 | 行业数据源 / 定期手工维护 |

**设计要点（展望级，实施前出详细设计）**：
- **前端**：Streamlit 多页导航（`st.navigation`），左侧菜单【投研顾问】【市场监控】；监控面板按维度分类展示 + 重要度标记 + 时间线
- **采集调度**：每日定时任务（APScheduler 或外部调度），采集器按数据源插件化（统一 Collector 接口）
- **存储**：SQLite 事件表（Pydantic 模型规范），URL/内容 hash 去重；持仓配置管理
- **与一期衔接**：监控事件可一键入库知识库（复用 indexer），投研顾问对话时可引用监控事件
- **容错**：单数据源失败不影响整体，采集结果带时间戳与来源标记

## 7. 三期展望（仅记录，不实现）

- 工具调用：LLM client 抽象层支持 function calling；首批工具=联网搜索（Tavily，`TAVILY_API_KEY` 已在密钥清单）
- ReAct 循环：pipeline 层实现「思考→行动→观察」状态机，工具注册表 + 最大迭代数熔断

## 8. 四期展望（仅记录，不实现）

- **短期记忆**：会话内消息历史，滑动窗口 + 超限摘要压缩
- **长期记忆**：Chroma 独立 `memory` collection，对话结论向量化存储，按相似度回填
- **上下文管理**：统一 `ContextBuilder`，按优先级组装（system → 长期记忆 → RAG 检索 → 近期对话）并分配 token 预算
- **与三期衔接**：ReAct 的 scratchpad（中间思考/工具观察结果）也纳入 ContextBuilder 统一管理

## 9. 五期展望（仅记录，不实现）

**多 Agent 编排**：同一 RAG 检索核心 × 不同投资思维角色 Agent，编排层汇总裁决。首批角色：

| 角色 | 思维框架要点 |
|---|---|
| 查理·芒格「格栅思维」投资者 | 多学科思维模型交叉验证，避免单一学科偏见，反过来想 |
| 沃尔特·施洛斯「纯价值」投资者 | 低估值量化筛选（低 PB/PE、资产负债表稳健），分散持股，不预测市场 |
| 巴菲特「护城河」投资者 | 商业模式与竞争优势分析（品牌/成本/网络效应/转换成本），长期持有 |
| 邓普顿「逆向」投资者 | 极度悲观点买入、极度乐观点卖出，全球化分散视角 |
| 霍华德·马克斯「周期」投资者 | 市场周期位置判断，钟摆思维，风险温度计 |

**架构含义（反推前期的约束）**：
- 每个 Agent = 角色化 system prompt（思维框架 + 分析清单）+ 共享的检索与记忆能力
- 一期 `pipeline.rag` 作为 prompt 组装唯一收口的设计必须保持，五期只需实例化多个 pipeline 配置不同角色 prompt
- 编排层负责：问题分发 → 各角色独立分析 → 观点冲突呈现 → 综合裁决（可再配一个「主持人」Agent）
- **与二期衔接**：监控事件流是各角色 Agent 的共同「观察输入」之一

## 10. 六期展望（仅记录，不实现）

**目标**：财报/研报信息的深度解读 + 财务计算的确定性执行。

**两个核心能力**：

1. **财报/研报优化解读**
   - 针对财报 PDF 的表格解析增强（一期 pypdf 纯文本抽取对表格损耗大，六期引入表格感知解析，如 camelot/pdfplumber）
   - 财务数据结构化抽取：三大报表科目 → Pydantic 模型（复用一期 models.py 规范）→ 独立存储，供计算层调用
   - 研报元数据抽取：评级/目标价/盈利预测表

2. **PTC（Programmatic Tool Calling）确定性计算**
   - 区别于逐次 function calling：LLM 生成一段完整 Python 计算程序，沙箱内**一次性确定性执行**，杜绝大模型心算误差
   - 沙箱执行环境（受限 import、超时熔断、结果校验）
   - 预置估值函数库（带单元测试的确定性实现，LLM 只负责选参数不负责算数）：
     - 自由现金流折现（DCF/WACC）
     - 清算价值（Graham 净净值法等）
     - 可扩展：DDM、可比估值、PB-ROE 等
   - 计算结果回填 prompt，由 LLM 结合上下文做定性解读

**架构衔接**：PTC 本质是三期「工具调用」的进化形态——工具从"单次函数调用"升级为"整段程序调用"；财务结构化数据是四期长期记忆中事实数据的高置信来源。一期只需保证 ingest 层 loader 可替换（六期换表格感知解析器）和 models.py 的 Pydantic 模型规范。
