# 三期实施计划：工具调用 + ReAct（2026-11-02）

> 设计见 `2026-11-02-agent-react-design.md`。格式沿用一/二期：每任务 = 失败测试 → 最小实现 → 质量门禁 → 提交。全程无网络无 Key（e2e 除外）。

## 任务清单

### T1 models 扩展：RagAnswer.trace + 引用构建共享
- 测试：`tests/unit/test_models.py` 增 trace 默认空列表、带 TraceStep 构造；老构造调用全兼容
- 实现：`app/models.py` 新增 `TraceStep(step: int, tool: str, arguments: dict, observation: str)` 与 `RagAnswer.trace: list[TraceStep] = []`；`rag.py` 的 `_build_citations` 改为接收 `(reply, sources: list[tuple[str, str]])` 或提取到共享模块 `app/pipeline/citations.py`（agent/rag 共用，签名保持 chunks 版兼容）
- 提交：`feat: RagAnswer 增加决策轨迹字段，引用构建提取共享`

### T2 工具层基座：ToolSpec / ToolResult / Evidence / ToolRegistry
- 测试：`tests/unit/test_tool_registry.py`：注册后 get 命中；重名注册抛 ValueError；get 未注册返回 None；`openai_tools()` 输出 `[{"type":"function","function":{name,description,parameters}}]`
- 实现：`app/tools/base.py`（Pydantic：`Evidence(source: str, text: str)`；frozen dataclass ToolSpec/ToolResult；Tool Protocol）+ `app/tools/registry.py`
- 提交：`feat: 工具注册表与 Tool Protocol 基座`

### T3 knowledge_search 工具
- 测试：`tests/unit/test_knowledge_search_tool.py`：FakeRetriever 返回 2 切片 → ToolResult.evidence 2 条（source/text 对应）、text 含切片正文；检索空 → evidence=[]、text 提示无内容；retriever 抛异常 → 失败文本降级不抛出
- 实现：`app/tools/knowledge_search.py`，spec.parameters = `{"type":"object","properties":{"query":{"type":"string","description":...}},"required":["query"]}`
- 提交：`feat: knowledge_search 工具——包装一期 Retriever`

### T4 LLM 客户端 chat_with_tools
- 测试：`tests/unit/test_llm_client.py` 增：mock OpenAI 响应含 tool_calls（JSON 字符串参数）→ ChatResponse.tool_calls 映射正确；无 tool_calls → content 透传；arguments 非法 JSON → arguments={}；`LLMClient` Protocol runtime_checkable 兼容旧 FakeLLM（只实现 chat 的测试替身不再满足 Protocol——**决策：Protocol 只加方法不改 runtime 断言用法，测试替身按需补 chat_with_tools**）
- 实现：`app/llm/client.py` 新增 `ToolCall`/`ChatResponse`（Pydantic）、Protocol 方法、DeepSeekClient 实现（复用 tenacity 重试）
- 提交：`feat: LLM 客户端支持 function calling（chat_with_tools）`

### T5 AgentPipeline ReAct 循环（核心）
- 测试：`tests/unit/test_agent_pipeline.py`，FakeLLM 按脚本序列返回 ChatResponse：
  1. 直接终答（无 tool_calls）→ RagAnswer.answer 透传、trace 空
  2. 单工具单轮：第 1 轮返回 tool_call(knowledge_search)，第 2 轮终答含 `[1]` → citations 1 条、trace 1 步、messages 含 role=tool 消息
  3. 多轮两工具 → 证据编号全局递增 [1][2][3]，终答按标注过滤
  4. 未注册工具名 → 观察文本含"未知工具"，循环继续不崩
  5. 每轮都调工具 → max_iterations 次后走 `llm.chat` 强制终答，citations=全部证据
  6. 工具返回失败文本 → 正常回填，循环继续
- 实现：`app/pipeline/agent.py` + `app/pipeline/prompts.py` 增 `AGENT_SYSTEM_PROMPT`（含"有工具优先查证、无把握不编造、引用 [n] 标注"）
- 提交：`feat: AgentPipeline——ReAct 工具调用循环与全局证据编号`

### T6 web_search 工具（Tavily）
- 测试：`tests/unit/test_web_search_tool.py`：monkeypatch httpx.post → 正常 JSON（results: title/content/url）映射 Evidence(source=url)；HTTP 状态异常/网络异常 → 失败文本降级；空 Key 构造抛 ValueError（factory 层负责不注册，工具自身防御）
- 实现：`app/tools/web_search.py`（httpx 同步 POST，timeout 15s，`tavily_max_results` 注入）；`pyproject.toml` 加 `httpx>=0.27`
- 提交：`feat: web_search 工具——Tavily 联网搜索，异常降级`

### T7 config + factory 接线
- 测试：`tests/unit/test_factory.py` 增：monkeypatch settings（tavily_api_key 空/非空）→ build_agent_pipeline 注册表工具数 1/2；`tests/unit/test_config.py` 增新字段默认值
- 实现：`config.py` 三新字段；`factory.py` `build_agent_pipeline()`（复用现有组装 + KnowledgeSearchTool 必注册 + Tavily 按 Key 注册）
- 提交：`feat: factory 组装 AgentPipeline，Tavily 按 Key 降级注册`

### T8 UI / CLI 接线
- advisor.py：换 build_agent_pipeline；回答下 `st.expander("🧠 决策轨迹")` 逐步显示 `TraceStep`；citations 渲染兼容 URL source（web 证据可点击）
- cli.py：换 build_agent_pipeline；轨迹行打印；运行时容错不变
- 测试：AppTest 渲染 advisor 无异常（沿用二期 monitor 页验证手法）；cli 单测更新 FakePipeline 带 trace
- 提交：`feat: 投研顾问/CLI 接入 Agent，展示决策轨迹`

### T9 e2e + 文档回写
- `tests/e2e/test_agent_smoke.py`（需 DEEPSEEK Key，自动 skip）：①"你好"→ 终答且 trace 空 ②知识库问题 → trace 含 knowledge_search
- 文档：DECISIONS.md D014 + [Unreleased] 变更记录；总设计 §7 标记三期完成；AGENTS.md 路线图/代码索引/测试索引刷新；monitor 设计文档不动
- 提交：`docs: 三期收口——D014、路线图与索引同步`

## 门禁

每任务提交前：`ruff check .` + `black --check .` + `mypy app` + `pytest tests/unit tests/integration`。

## 风险与预案

- DeepSeek tool_calls 返回格式偏差 → T4 用真实响应样例校准映射（开发期手工验证一次，单测仍用 mock）
- LLM 不调工具直接编造 → AGENT_SYSTEM_PROMPT 强化"涉及事实必查证"；温度 0.3
- 无 Tavily Key：用户需自行在 .env 加 `TAVILY_API_KEY`（免费额度 tavily.com），缺失不阻断
