# 本地 RAG 智能问答助手 — 设计文档

> 日期：2026-10-29 ｜ 项目：DeepFinResearch ｜ 状态：已确认

## 1. 产品愿景

基于本地知识库的智能问答助手（DeepFinResearch），三期演进：

- **一期（本期）**：RAG 问答 —— 文档入库 → 向量检索 → prompt 拼接 → LLM 回复（带引用）+ Streamlit 界面
- **二期**：工具调用（联网搜索等）+ ReAct 自主决策循环
- **三期**：上下文与状态管理，短期/长期记忆，Agent 具备记忆能力
- **四期**：多 Agent 编排，引入不同投资思维角色的 Agent（详见 §8）

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
    client.py      # DeepSeek chat（接口抽象，二期可换/加模型）
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

1. **二期/三期预留原则（YAGNI）**：一期只保证两点——`pipeline.rag` 是所有 prompt 组装的唯一收口；LLM client 走接口抽象。二期 ReAct 在 pipeline 层加循环，三期在此插入 ContextBuilder，UI 与检索层不动。工具注册等一概不提前实现。
2. **Prompt 策略**：system prompt 强制「仅依据上下文回答，检索不到就明说」；回复内联标注来源 `[1][2]`，附引用列表（文档名 + 片段）。
3. **错误处理**：
   - LLM/Embedding API 调用用 tenacity 指数退避重试；
   - 检索结果为空或全部低于阈值 → 明确告知「知识库中未找到相关内容」，不硬答；
   - 入库按内容 SHA256 去重，重复文档跳过；
   - `.env` 缺必需密钥 → 启动即报错退出。
4. **测试策略（TDD）**：unit（mock LLM/embedding，测 splitter 切分边界、prompt 构建、去重逻辑）；integration（真实 Chroma：入库/检索/过滤）；e2e 冒烟（真实 API，可跳过标记 `@pytest.mark.e2e`）。

## 6. 二期展望（仅记录，不实现）

- 工具调用：LLM client 抽象层支持 function calling；首批工具=联网搜索（Tavily，`TAVILY_API_KEY` 已在密钥清单）
- ReAct 循环：pipeline 层实现「思考→行动→观察」状态机，工具注册表 + 最大迭代数熔断

## 7. 三期展望（仅记录，不实现）

- **短期记忆**：会话内消息历史，滑动窗口 + 超限摘要压缩
- **长期记忆**：Chroma 独立 `memory` collection，对话结论向量化存储，按相似度回填
- **上下文管理**：统一 `ContextBuilder`，按优先级组装（system → 长期记忆 → RAG 检索 → 近期对话）并分配 token 预算
- **与二期衔接**：ReAct 的 scratchpad（中间思考/工具观察结果）也纳入 ContextBuilder 统一管理

## 8. 四期展望（仅记录，不实现）

**多 Agent 编排**：同一 RAG 检索核心 × 不同投资思维角色 Agent，编排层汇总裁决。首批角色：

| 角色 | 思维框架要点 |
|---|---|
| 查理·芒格「格栅思维」投资者 | 多学科思维模型交叉验证，避免单一学科偏见，反过来想 |
| 沃尔特·施洛斯「纯价值」投资者 | 低估值量化筛选（低 PB/PE、资产负债表稳健），分散持股，不预测市场 |
| 巴菲特「护城河」投资者 | 商业模式与竞争优势分析（品牌/成本/网络效应/转换成本），长期持有 |
| 邓普顿「逆向」投资者 | 极度悲观点买入、极度乐观点卖出，全球化分散视角 |
| 霍华德·马克斯「周期」投资者 | 市场周期位置判断，钟摆思维，风险温度计 |

**架构含义（反推一期的约束）**：
- 每个 Agent = 角色化 system prompt（思维框架 + 分析清单）+ 共享的检索与记忆能力
- 一期 `pipeline.rag` 作为 prompt 组装唯一收口的设计必须保持，四期只需实例化多个 pipeline 配置不同角色 prompt
- 编排层负责：问题分发 → 各角色独立分析 → 观点冲突呈现 → 综合裁决（可再配一个「主持人」Agent）
