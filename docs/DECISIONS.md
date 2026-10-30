# 项目决策日志

> 记录所有影响项目方向的决策：背景、选项、结论、理由。新决策追加在末尾，**只增不改**（推翻旧决策时新增条目并注明取代关系）。
> 配套文档：设计文档 `docs/plans/`、变更记录 `CHANGELOG.md`。

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

建立本日志：所有影响方向/架构/范围的决策单独记录于 `docs/DECISIONS.md`，只增不改，便于后续梳理项目思路。工程执行类细节仍在 CHANGELOG 与设计文档中。
