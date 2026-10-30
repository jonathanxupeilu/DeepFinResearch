# Changelog

本项目所有显著变更记录于此文件。
格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed
- **embedding 截断保护**：截断上限由 6000 字符修正为 12000 字符，依据官方
  text-embedding-v3 单条 8192 token 限制（中文 ~1.5 字符/token 保守换算），
  注明出处（`app/llm/embedding.py`）

### Added
- **引用精确解析**：回答中实际标注 `[n]` 才保留对应引用来源；越界编号忽略；
  无任何标注时保留全部来源不丢信息（`app/pipeline/rag.py`）

### Changed
- **Streamlit pipeline 缓存**：`webapp.py` 用 `st.cache_resource` 会话间复用
  pipeline（Chroma 连接/Embedder/LLM 客户端）；`factory.py` 保持框架无关
  以继续服务 CLI 与测试

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

[Unreleased]: https://github.com/jonathanxupeilu/DeepFinResearch/compare/v0.1.0...HEAD
[v0.1.0]: https://github.com/jonathanxupeilu/DeepFinResearch/releases/tag/v0.1.0
