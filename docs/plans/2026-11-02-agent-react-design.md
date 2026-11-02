# 三期设计：工具调用 + ReAct 自主决策（2026-11-02）

> 承接总设计 `2026-10-29-local-rag-qa-design.md` §7。目标：用「工具注册表 + ReAct 循环」取代一期闲聊正则分流，投研顾问从"单次检索问答"升级为"自主决定查什么、查几轮"的 Agent。

## 1. 目标与非目标

**目标**
- Agent 自主决策：LLM 通过 function calling 决定调用哪个工具（知识库检索 / 联网搜索）、是否多轮，最后综合作答
- 工具注册表插件化：新增工具只写一个类 + factory 注册一行，不动循环逻辑
- 最大迭代数熔断，防止工具调用死循环
- 引用体系升级：知识库切片与联网搜索结果统一编号为证据（evidence），回答中 [n] 标注，`RagAnswer.citations` 复用一期模型
- UI/CLI 展示决策轨迹（调用了哪些工具、每轮观察结果），可折叠

**非目标（YAGNI）**
- 不做记忆/上下文管理（四期）；不做多 Agent 角色（五期）；不做 PTC 程序化工具（六期）
- 不删除 `RAGPipeline`：保留为"单轮 RAG 快速通道"（e2e 冒烟、CLI 降级路径继续用），Agent 是新增入口而非改写
- 工具不做异步/并行调用：DeepSeek 单轮可能返回多个 tool_calls，串行执行即可

## 2. 架构

```
advisor.py / cli.py
      │
      ▼
factory.build_agent_pipeline()
      │  组装 ToolRegistry：KnowledgeSearchTool（必选）+ TavilySearchTool（有 Key 才注册）
      ▼
pipeline/agent.py  AgentPipeline.answer(question) -> RagAnswer
      │  ReAct 循环：messages + tools → llm.chat_with_tools()
      │    ├─ 返回 tool_calls → registry 执行 → 结果作为 tool 消息追加 + 证据编号 → 下一轮
      │    └─ 返回纯文本 → 终答，按 [n] 标注从证据表构建 citations
      ▼
llm/client.py  chat_with_tools(messages, tools) -> ChatResponse(content|tool_calls)
tools/         base.py（Tool Protocol + ToolSpec）/ registry.py / knowledge_search.py / web_search.py
```

**收口原则不破**：所有 prompt 组装仍收口在 `app/pipeline/`（rag.py 管单轮，agent.py 管循环）；`prompts.py` 新增 Agent 系统提示词与工具描述文案常量。

## 3. 工具层设计（`app/tools/`）

```python
# base.py
@dataclass(frozen=True)
class ToolSpec:
    name: str                 # LLM 可见的工具名，如 "knowledge_search"
    description: str          # 何时该用这个工具（LLM 决策依据）
    parameters: dict[str, Any]  # JSON Schema

class Tool(Protocol):
    spec: ToolSpec
    def run(self, arguments: dict[str, Any]) -> ToolResult: ...

@dataclass(frozen=True)
class ToolResult:
    text: str                 # 回填给 LLM 的观察文本（已含 [n] 证据编号）
    evidence: list[Evidence]  # 本轮新增证据（source + text），进 citations 候选池
```

| 工具 | 说明 | 证据来源 |
|---|---|---|
| `knowledge_search` | 包装一期 `Retriever`，query 参数；返回 top-k 切片，每条前缀全局证据编号 `[n]（来源: xxx）` | 知识库文档 source |
| `web_search` | Tavily REST（httpx POST `api.tavily.com/search`），query 参数；返回标题+摘要+URL | 结果 URL |

- **证据编号是全局递增的**：由 AgentPipeline 持有的计数器统一分配（工具内部不知道全局编号，返回 Evidence 列表，循环层编号后拼进观察文本）。→ 修正：`Tool.run` 返回**未编号**的 Evidence，观察文本的编号由循环层完成，工具保持纯粹。
- **容错**：工具内部 catch 全部异常，失败返回 `ToolResult(text="工具调用失败: <原因>", evidence=[])`，让 LLM 自己决定换路还是放弃，循环不崩。
- **web_search 降级**：`TAVILY_API_KEY` 缺失/为空时 factory 不注册该工具，Agent 只剩知识库检索，系统提示词同步不含联网能力描述。

## 4. LLM 客户端扩展（`app/llm/client.py`）

```python
class ToolCall(BaseModel):        # Pydantic v2，禁裸 dict
    id: str
    name: str
    arguments: dict[str, Any]     # 从 JSON 字符串解析，解析失败 arguments={}

class ChatResponse(BaseModel):
    content: str                  # 终答文本；有 tool_calls 时通常为空
    tool_calls: list[ToolCall]

class LLMClient(Protocol):        # 原 chat() 签名不变，一期测试全兼容
    def chat(self, messages, temperature=0.7) -> str: ...
    def chat_with_tools(self, messages, tools: list[dict], temperature=0.3) -> ChatResponse: ...
```

`DeepSeekClient.chat_with_tools`：`chat.completions.create(..., tools=tools, tool_choice="auto")`，把响应中的 `tool_calls` 映射为 `ToolCall`；沿用 chat 的 tenacity 重试装饰器。

## 5. ReAct 循环（`app/pipeline/agent.py`）

```
answer(question):
  messages = [system(AGENT_SYSTEM_PROMPT), user(question)]
  evidence: list[Evidence] = []           # 全局证据池
  for i in range(max_iterations):          # 熔断，默认 5（settings.agent_max_iterations）
      resp = llm.chat_with_tools(messages, registry.openai_tools())
      if not resp.tool_calls:
          return RagAnswer(answer=resp.content, citations=_build_citations(resp.content, evidence))
      messages.append(assistant 消息含 tool_calls 原文)
      for tc in resp.tool_calls:
          tool = registry.get(tc.name)     # 未注册工具名 → 观察文本报错，继续循环
          result = tool.run(tc.arguments)
          为 result.evidence 分配全局编号 [n]，拼观察文本
          messages.append({"role":"tool", "tool_call_id": tc.id, "content": 观察文本})
          evidence += result.evidence
  # 熔断兜底：最后一轮不带 tools 强制终答
  resp = llm.chat(messages)
  return RagAnswer(answer=resp, citations=全部证据)
```

- **闲聊分流取代**：Agent 入口不再跑 `is_smalltalk` 正则——打招呼类输入 LLM 直接终答不调工具。`rag.py` 单轮通道保留正则（其定位不变）。
- **无证据诚实拒答**：终答后若 evidence 为空且回答含"未找到"类表述，不强加 citations（复用一期 `_build_citations` 语义：没标 [n] 则保留全部；evidence 为空自然得空列表）。
- **引用构建**：`agent.py` 复用 `rag.py` 的 `_CITE_RE` 抽取逻辑（提取为模块级函数避免复制）。

## 6. 配置与组装

`config.py` 新增（全部有默认值，老 .env 不破）：
```python
tavily_api_key: str = ""          # 空 = 不注册 web_search
agent_max_iterations: int = 5
tavily_max_results: int = 5
```

`factory.py` 新增 `build_agent_pipeline() -> AgentPipeline`：复用 build_pipeline 的 store/embedder/retriever/llm 组装，套上 ToolRegistry。`pyproject.toml` 依赖新增 `httpx>=0.27`（openai 已传递引入，显式声明）。

## 7. UI / CLI

- **advisor.py**：`st.cache_resource` 换 build_agent_pipeline；回答下方 `st.expander("🧠 决策轨迹")` 展示每轮"调用工具 → 观察摘要"；citations 渲染不变（web 证据 source 即 URL，可点击）
- **cli.py**：轨迹逐行打印 `[工具] knowledge_search(query=...) → 3 条证据`；终答与引用格式不变
- `RagAnswer` 增加 `trace: list[TraceStep] = []`（Pydantic 默认值，老构造全兼容）：`TraceStep(step, tool, arguments, observation_summary)`

## 8. 测试策略（TDD，全部无网络无 Key）

| 层 | 用例要点 |
|---|---|
| tools/base+registry | 注册/重名拒绝/get 未注册返回 None/openai_tools() 格式 |
| knowledge_search | FakeRetriever 注入；证据文本含来源；检索空返回无证据 |
| web_search | mock httpx（monkeypatch）；正常结果映射 Evidence(url)；HTTP 异常降级失败文本；无 Key 构造即拒绝 |
| llm client | mock OpenAI SDK：tool_calls 响应 → ChatResponse 映射；JSON 参数解析失败 arguments={} |
| agent 循环 | FakeLLM 脚本化响应序列：①直接终答 ②单工具单轮 ③多轮 ④未注册工具名容错 ⑤max_iterations 熔断走强制终答 ⑥citations 按 [n] 过滤、编号全局递增 |
| factory | monkeypatch settings：有/无 tavily_api_key 时注册表工具数 |
| e2e（需 Key，自动 skip） | 真实 DeepSeek："你好"不调工具；"知识库里关于XX说了什么"调 knowledge_search |

## 9. 实施顺序（对应实施计划文档）

1. `RagAnswer.trace` + `_build_citations` 提取共享 → 2. tools/base+registry → 3. knowledge_search → 4. llm chat_with_tools → 5. agent 循环 → 6. web_search（Tavily） → 7. factory+config → 8. UI/CLI 接线 → 9. e2e + 文档回写（DECISIONS D014、AGENTS.md、总设计 §7 标记完成）

## 10. 决策记录（回写 DECISIONS.md 为 D014）

- **原生 function calling 而非文本协议 ReAct**：DeepSeek 官方支持 tools 参数，JSON 结构化远比解析 "Action:/Observation:" 文本鲁棒；"思考"过程由轨迹（工具调用序列）显式呈现，不要求 LLM 输出 Thought 文本
- **AgentPipeline 新增而非改写 RAGPipeline**：单轮 RAG 是 Agent 的退化形态且有独立价值（快、省 token、e2e 基线）；一期"rag.py 唯一收口"约束升级为"pipeline 包唯一收口"
- **证据编号全局分配**：跨工具跨轮次统一 [n]，保证终答引用与 citations 一一对应
- **Tavily 无 Key 静默降级**：不阻断启动，Agent 能力随配置伸缩

## 11. 实施修订（2026-11-02 · 时间锚定与"先事实后原因"）

**优化前**（用户实测反馈）：问「A股黄金板块最近波动为什么这么大」，Agent 虽调用了知识库+联网搜索，但回答泛泛而谈——没有时间区间定位、没说清波动是涨是跌，堆砌通用原因。

**根因**：① LLM 无当前日期概念，「最近」无法解析成具体区间，搜索 query 带不上时间词；② 提示词只要求"查证后回答"，未要求先定位事实（区间/方向/幅度）再分析原因；③ Tavily 支持 time_range 收缩时间窗但工具未暴露。

**优化后**：
1. **动态日期注入**：`AgentPipeline._system_message()` 在系统提示词末尾追加「今天是 YYYY-MM-DD（北京时间，星期X）」，作为「最近/近期/今天」的解析基准（北京时间 = UTC+8，不依赖系统时区库）
2. **提示词新增规则 3/4/7**：时间词问题必须先查证具体事实（区间/方向/幅度/关键事件）再分析原因；联网 query 必须带明确时间词、近期行情传 time_range；行情类回答先给事实概要再展开
3. **web_search 暴露 time_range**：可选参数 day/week/month/year 透传 Tavily（真实调用验证通过），非法值忽略

**最新设计**：AGENT_SYSTEM_PROMPT 保持静态常量（规则），日期行运行时拼接——五期注入角色 prompt 时同样自动获得时间锚点。

## 12. 实施修订二（2026-11-02 · 时间获取工具化，D016）

**优化前**（§11 方案）：系统消息运行时写死追加「今天是 YYYY-MM-DD」日期行。

**用户反馈**：应让 Agent 自主判断是否调用「获取当前时间」工具，而不是写死时间。

**优化后**：
1. 新增 `app/tools/current_time.py`：无参数工具，返回「当前北京时间：YYYY-MM-DD HH:MM（星期X）」；注入时钟语义 = 返回 UTC，+8 换算归工具（测试用固定时钟验证）
2. `agent.py` 撤销 `_system_message()` 动态日期行，系统消息回到静态 AGENT_SYSTEM_PROMPT
3. 提示词规则 3：明确「你没有当前时间的概念」，时间词问题必须先调 current_time；规则 5 的时间词以 current_time 结果为准
4. factory 无条件注册 current_time（无 Key 也具备：knowledge_search + current_time）；advisor 页工具标签「🕐 当前时间」

**取舍**：多一轮工具调用（时间敏感问题）换取架构一致性——工具能力全部经注册表声明、由 LLM 自主决策，系统提示词保持静态常量，五期角色 prompt 复用无副作用。

## 13. 踩坑与优化记录（2026-11-02 当日）

**回答质量优化三步演进**（用户实测驱动）：
1. 三期上线 → 实测「A股黄金板块最近波动为什么这么大」回答泛泛而谈：无时间区间、未说明涨跌方向
2. 根因：LLM 无当前时间概念，「最近」解析不了 → D015 系统消息写死注入日期行 + 「先事实后原因」规则 + Tavily time_range
3. 用户反馈「应让 Agent 自主判断是否调用获取时间工具，而非写死」→ D016 撤销注入，新增 current_time 工具，提示词明示「你没有当前时间的概念」

**工程踩坑**：
- `.env` 分隔符：`TAVILY_API_KEY:值`（冒号）无效——pydantic-settings 只认 `=`；症状是 grep 能看到 Key 名但 Settings 读到空串、web_search 静默未注册。排查手法：只打印值长度不打印值
- `MagicMock(id=..., name=...)` 构造参数是 mock 元信息**不会**设置 `.id`/`.name` 属性，必须显式赋值，否则 Pydantic 校验收到 MagicMock 对象报错
- Protocol 成员声明为 `run: Callable[...]` 属性时，mypy 要求"可写变量"，普通类方法（只读）不满足——Tool Protocol 的 run 必须用方法语法声明
- ruff RUF100：noqa 引用未启用的规则（如 A002）本身会报错
- 被 black 重排过的文件再 Edit 会因 old_string 不匹配失败，编辑前先重新 Read
- Tavily：Bearer 鉴权 + `time_range` 参数均经真实调用验证；工具层异常一律降级为观察文本，循环不崩

**prompt 收口补全**：工具 description/参数描述（LLM 决策依据，本质是 prompt）从各工具文件迁入 prompts.py 常量——手动调优任何 prompt（系统提示词/文案/工具话术）只改 prompts.py 一个文件。
