# 四期·第一步：观测平台技术选型可行性调研（Litefuse）

> 日期：2026-11-04 ｜ 状态：**已确认定案 LangSmith（D019），待按 §10.4 PoC 开工**；Litefuse（§1-§8）与 Helicone（§9）调研留档作决策记录
> 背景：四期 Evals 评估体系（D018）的第一步是搭建 LLM 观测平台，用户指定技术选型 Litefuse。本文档为可行性调研结论 + 接入方案草案，非实施计划（实施计划待立项后按 phase 文档格式另出）。

## 1. 结论（TL;DR）

**最终结论（2026-11-04 二次修订）：采用 LangSmith Developer 免费档（云端、零部署），`wrap_openai` + `@traceable` 接入，详见 §10。**

决策路径：Litefuse 自部署（过重，否决）→ Helicone 网关（工具链路盲区 + 评估能力弱，被 §10 取代）→ LangSmith（观测 + 四期 Evals 一站式覆盖）。

<details>
<summary>原 Litefuse 结论（已否决，留档）</summary>

可行，建议采用，但带两个前置条件：

1. **本地 Docker Compose 自部署先跑 PoC**，验证 Windows + Docker Desktop 下资源占用可接受（Doris 组件偏重）；
2. **SDK 层只依赖 `langfuse` PyPI 包**（Litefuse 官方 SDK 就是它），保持随时可平移回 Langfuse 平台的退路。

Litefuse 满足四期全部观测需求：Trace（模型调用/工具调用/检索链路）、Token 与耗时统计、Datasets 测评集、LLM-as-a-judge / 人工标注 / 自定义 Score，且 MIT 许可、可完全自托管（数据不出本机，符合本项目本地知识库定位）。

</details>

## 2. Litefuse 是什么

| 项 | 内容 |
|---|---|
| 定位 | 开源 Agent 可观测与评估平台（LLM 工程平台） |
| 出品方 | 飞轮科技（SelectDB，Apache Doris 商业化公司） |
| 技术底座 | Apache Doris（分析存储）+ Postgres（元数据）+ Redis（队列）+ MinIO/S3（原始载荷） |
| 与 Langfuse 关系 | **Langfuse 的衍生/改名项目**：LICENSE 版权头为 "Copyright (c) 2023-2025 Langfuse GmbH"，README/文档结构与 Langfuse 高度一致，宣称单机版比 Langfuse 快 5.5 倍、存储更省 |
| 许可证 | MIT（含第三方组件各自原始许可；GitHub 显示 NOASSERTION 是因混合声明） |
| 成熟度 | GitHub 107 星，2026-04 创建，2026-10 仍在推送；TypeScript；有 SaaS（litefuse.cloud，免费额度） |
| 部署方式 | 一行脚本单机版（Linux/Mac，约 25 秒）/ Docker Compose / K8s Helm / Terraform（AWS/Azure/GCP） |

**关键事实：Litefuse 没有自己的 Python SDK**——官方文档直接指向 `pip install langfuse`（Langfuse Python SDK v3，OpenTelemetry 架构），环境变量沿用 `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL`，只是 BASE_URL 指向 Litefuse 实例。这意味着：

- SDK 侧成熟度 = Langfuse SDK 成熟度（生产验证充分）；
- 应用代码不绑定 Litefuse，平台层可替换（Langfuse / 其他兼容 OTel 的后端）。

自部署版本约束：Python SDK v3 要求平台版本 ≥ 3.125.0。

## 3. 功能与四期需求对照

| 四期需求 | Litefuse 能力 | 匹配度 |
|---|---|---|
| 记录 Agent 每次问答的完整链路 | Tracing：generation（LLM 调用，含 model/tokens/cost）、span（工具调用、检索）、event；trace 级 session_id/user_id/tags | ✅ 直接匹配三期 AgentPipeline 的 ReAct 循环结构 |
| 耗时/Token/成本分析 | 自动采集，Dashboard 聚合 | ✅ |
| 测评集（Evals 数据集） | Datasets + Dataset Runs，支持 SDK 创建与回放实验 | ✅ 四期后续步骤的载体 |
| 打分/评估 | LLM-as-a-judge、人工标注队列、用户反馈、API/SDK 自定义 Score | ✅ |
| Prompt 迭代 | Prompt Management（版本化、灰度） | ⚠️ **本期不用**：项目已定 `prompts.yaml` 为唯一收口（D017 相关），不迁移 prompt 管理，避免双源 |
| Bad case 复现调试 | Trace 详情页 → Playground 跳转 | ✅ |

## 4. 接入方案草案（与本项目代码的映射）

原则：**观测是旁路，不改变任何业务行为**；缺配置时静默降级（对齐 `web_search` 工具的可选注册模式）。

### 4.1 配置层（app/config.py）

新增三个可选配置项（Pydantic Settings，从 .env 读取）：

```
LITEFUSE_ENABLED / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL
```

Key 缺失或 enabled=false 时，所有埋点函数退化为 no-op，234 个存量测试不受影响（测试环境天然无 Key）。

### 4.2 埋点层（建议新增 app/observability.py 单模块收口）

不在业务代码里散落 `langfuse` import，统一经一个薄封装（`trace_question / trace_generation / trace_tool / flush`），内部判断开关。收口理由与 prompts.yaml 相同：可替换、可测试（mock 单模块即可）。

### 4.3 埋点位置（三处，按价值排序）

| 位置 | 埋什么 | 方式 |
|---|---|---|
| `app/pipeline/agent.py` ReAct 循环 | 一次 `answer()` = 一个 trace；每轮迭代 = span；每次工具执行 = tool span（输入参数/观察文本/耗时）；终答 = trace output | 手动埋点（context manager），与现有 TraceStep 决策轨迹一一对应 |
| `app/llm/client.py` DeepSeekClient | 每次 chat / chat_with_tools = generation（model、messages、tokens、耗时） | 两选一：① `from langfuse.openai import OpenAI` drop-in 替换（零逻辑改动，自动采集 usage）；② 手动 generation 埋点。**建议 ①**，本类已用 openai SDK |
| `app/pipeline/rag.py` | 单轮 RAG 通道：检索 span（query/top-k/相似度）+ generation | 手动埋点，e2e 基线链路对照组 |

session_id 复用 `chat_store` 的会话 id，advisor 页多轮对话在平台上可串成 session；`retrieval`/`ingest` 链路本期不埋（价值低，入库是离线批处理）。

### 4.4 进程模型注意点

- CLI（`app.cli`）与采集脚本是短生命周期进程，退出前必须 `flush()`，否则丢 trace；
- Streamlit 是长进程，SDK 后台异步批量上报，几乎无延迟开销（OTel 异步导出）。

## 5. 部署方案（本机 Windows）

**推荐：Docker Compose 自部署**（一行脚本单机版仅 Linux/Mac，Windows 不适用）。

```bash
git clone https://github.com/litefuse/litefuse.git
cd litefuse && docker compose up -d
```

组件与资源预估（Docker Desktop / WSL2）：

| 容器 | 作用 | 预估内存 |
|---|---|---|
| litefuse-web | UI + API | ~512MB |
| litefuse-worker | 异步入库/后台任务 | ~512MB |
| Postgres | 元数据 | ~256MB |
| Redis | 队列/缓存 | ~128MB |
| MinIO | 原始载荷对象存储 | ~256MB |
| **Doris (FE+BE)** | 分析存储 | **2-4GB（大头）** |

合计约 4-6GB 内存。**风险点**：Doris BE 默认 JVM/内存配置偏大，PoC 时需确认与本机现有服务（Chroma、Streamlit、IDE）共存无压力；若过重，备选降级路径为 litefuse.cloud 免费档（数据出本机，与本地知识库隐私定位冲突，仅作兜底）。

生产注意（官方清单）：全部容器 `TZ=UTC`；健康检查 `/api/public/health`；web 与 worker 镜像同 TAG。

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 项目年轻（107 星、2026-04 创建），社区小、迭代不确定 | 中 | SDK 是成熟的 `langfuse` 包 + OTel 标准协议，应用侧零绑定；平台层可平移回 Langfuse（迁移成本≈改 BASE_URL） |
| Doris 内存占用重（Windows/WSL2 下 4-6GB） | 中 | PoC 第一步就验证；不可接受则评估 cloud 免费档或 Langfuse 自部署（ClickHouse 底座，资源画像已知） |
| 文档品牌混乱（Litefuse 文档内大量 Langfuse 字样、链接指向 langfuse 资产） | 低 | 实际按 Langfuse 文档理解即可，反而资料更全 |
| LICENSE 为 MIT + 第三方混合声明，GitHub 标 NOASSERTION | 低 | 核心为 MIT Expat，本地自用无合规问题；若未来商用需复核 ee 类目录（当前仓库未见 ee 拆分） |
| 与三期已有 TraceStep 决策轨迹功能重叠 | 低 | 定位不同：TraceStep 是用户可见的回答附录，Litefuse 是开发侧全量观测；并存不冲突，埋点数据源可复用 |

## 7. 建议的 PoC 验证步骤（立项后执行）

1. Docker Compose 起 Litefuse，记录冷启动时长与稳态内存；
2. `pip install langfuse`（用 uv），config.py 加可选配置 + observability.py 薄封装；
3. 先只埋 `llm/client.py`（drop-in OpenAI wrapper），CLI 问一个问题，平台上看到第一条 generation trace；
4. 再埋 `agent.py` ReAct 循环，验证多轮迭代/工具 span 层级正确、session 串联正确；
5. 用 SDK 建一个 3 条样本的 Dataset 跑通「测评集→回放→打分」最小闭环，为四期后续步骤探路；
6. 全程 TDD：observability 封装的开关/no-op/降级行为先写单测。

## 8. 调研来源

- GitHub: litefuse/litefuse（README、LICENSE、仓库元数据，2026-11-04 抓取）
- Litefuse 官方文档: litefuse.ai/docs/sdk（Python SDK 快速开始/配置/OTel 架构）、litefuse.ai/self-hosting（部署方式/架构/生产清单）
- ITPUB/SelectDB：「Litefuse 开源：一行命令部署 Agent 可观测与评估平台，单机版比 Langfuse 快 5.5 倍」（2026-06-23）
- 阿里云开发者社区：Apache Doris AI 可观测 Meetup（Litefuse 兼容 Langfuse SDK/OTel 接入，出品方飞轮科技）
- promptquorum.com：Langfuse 评测（许可证结构、Cloud 定价参照）

## 9. 选型修订一（2026-11-04）：降级为 Helicone（**已被 §10 取代，留档**）

**修订理由**：本项目为个人开发者本地项目，观测需求仅「看链路、看日志、看 Token 消耗」。Litefuse/Langfuse 自部署的 Doris/ClickHouse 底座（4-6GB 内存）属企业级配置，收益/成本不匹配，否决 §1 原结论。

### 9.1 轻量方案对比

| 方案 | 接入成本 | 运行成本 | 数据位置 | 评估能力 | 结论 |
|---|---|---|---|---|---|
| **Helicone 网关（推荐）** | `DeepSeekClient` 改 base_url + 加一个鉴权 header（OpenAI SDK `default_headers`），约 10 行 | 零部署；免费档约 10K 请求/月，个人用量足够 | Helicone 云（美国） | 请求日志/会话/成本看板齐全；datasets/LLM-as-judge 弱于 Langfuse 系 | ✅ **采用** |
| LangSmith | 非 base_url 直换，需 langsmith SDK `@traceable` 包装，侵入大于 Helicone | 零部署；免费 Developer 档 5K traces/月、保留 14 天 | LangChain 云 | 评估能力强 | 备选（免费额度和保留期偏紧） |
| 本地极简（OTel JSONL / 现有 TraceStep 落盘 + Streamlit 查看页） | 需自建落盘格式和 UI（约 1-2 个 TDD 任务） | 零 | 完全本地 | 无，四期评估需全自建 | 兜底（Helicone 不可用/隐私收紧时启用） |
| Litefuse / Langfuse 自部署 | 见 §4-§5 | Docker 常驻 4-6GB | 本地 | 最全 | ❌ 否决（过重） |

### 9.2 Helicone 接入要点（已核实官方文档）

Helicone 对 DeepSeek 有**官方专属网关**，接入即两行配置：

```
base_url: https://api.deepseek.com → https://deepseek.helicone.ai
headers:  Helicone-Auth: Bearer $HELICONE_API_KEY
```

对应本项目改动面（比原 Litefuse 方案更小）：

| 位置 | 改动 |
|---|---|
| `app/config.py` | 新增可选 `HELICONE_API_KEY`；`deepseek_base_url` 已有配置项，直接改值即可切换 |
| `app/llm/client.py` | `OpenAI(...)` 构造时：Key 存在则注入 `default_headers={"Helicone-Auth": ...}`；不存在则原样直连（降级 no-op，对齐 web_search 可选注册模式） |
| `app/pipeline/agent.py` | 可选：用 Helicone 的 `Helicone-Session-Id` / `Helicone-User-Id` header 把 chat_store 会话 id 串成 session（header 随请求透传，无需 SDK） |
| `.env.example` | 补 `HELICONE_API_KEY=`（可选） |

不需要 `app/observability.py` 独立模块（原 §4.2 作废）——网关模式下没有 SDK 埋点，全部观测由 header + 云端看板承担；工具调用/ReAct 迭代在请求体中原样可见（gateway 透传 function calling）。

### 9.3 修订后的风险表

| 风险 | 等级 | 缓解 |
|---|---|---|
| 每次 LLM 调用多一跳代理（延迟 + Helicone 可用性） | 中 | 现有 tenacity 重试已覆盖连接类故障；实测延迟不可接受则关 Key 直连（配置级开关，零代码回退） |
| prompt 含知识库切片，经 Helicone 云端（美国）存储 | 中 | 个人投研数据、非客户隐私数据，用户已接受云端方案；若日后收紧，切 §9.1 本地兜底方案 |
| 国内网络访问 helicone.ai 看板/网关的连通性 | 中 | PoC 第一步验证（网关走 API 直连通常无碍，看板浏览器访问可能需要代理） |
| 免费档 10K 请求/月，ReAct 一次问答消耗 3-8 个请求 | 低 | 个人用量估算月均 <2K 请求，余量充足；超限自动断观测不断服务（网关失败可降级直连） |
| 四期后续 Evals（datasets/打分）Helicone 能力弱 | 低 | 观测与评估解耦：第一步只看链路/Token；评估步骤到时再选（自建 pytest 测评集 or 换平台），不被本选型锁死 |

### 9.4 修订后的 PoC 步骤

1. 注册 helicone.ai 拿 API Key，浏览器确认看板可访问（国内连通性）；
2. config/client 两处小改（TDD：有 Key 注入 header、无 Key 直连、单测 mock OpenAI）；
3. CLI 问一个问题，看板确认出现请求记录（model/token/延迟/完整 messages）；
4. advisor 页多轮对话，验证 session header 串联效果；
5. 记录网关模式下的端到端延迟增量，超过 ~500ms 则评估直连+本地兜底。

### 9.5 新增来源

- Helicone 官方文档：DeepSeek 集成（docs.helicone.ai/getting-started/integration-method/deepseek）——专属网关 `deepseek.helicone.ai` + `Helicone-Auth` header
- Zuplo《Best AI Gateways 2026》：Helicone 免费档 10K 请求、一行 base_url 接入定位
- laminar.sh《Arize Phoenix Alternatives 2026》：Helicone 代理模式增加一跳的 tradeoff 佐证

## 10. 选型修订二（2026-11-04）：最终定案 LangSmith

**修订理由**：用户指出 LangSmith 更主流、14 天保留可接受、代码量不是约束。复核后确认两个决定性因素，Helicone 方案（§9）作废：

1. **工具级链路可见性**：Helicone 是 HTTP 网关，只能看到 LLM 请求；ReAct 循环中工具执行的耗时/参数/结果是盲区。LangSmith 通过 `wrap_openai` + `@traceable` 记录完整 Run 树（提问→迭代→工具 span→终答），四期要评的「工具选择正确率、参数正确率、任务完成率」依赖这份数据。
2. **四期 Evals 一站式覆盖**：LangSmith 原生提供 Datasets、LLM-as-judge、标注队列、`evaluate()` 实验 API，观测平台与评估体系同一工具闭环；Helicone 评估能力弱，后续需再引第二个平台。

### 10.1 免费档与计量口径（已核实）

| 项 | LangSmith Developer 免费档 |
|---|---|
| 席位 | 1（个人项目够用） |
| 额度 | 5,000 base traces/月 |
| 保留期 | 14 天（用户已接受；bad case 应及时沉淀进 Dataset——Dataset 存储不随 trace 过期） |
| 计量口径 | 按 trace（一次提问的整棵 Run 树 = 1 条），嵌套 LLM 调用/工具 span 不重复计数。对比 Helicone 按请求计数（ReAct 一次问答吃 3-8 请求），LangSmith 实际额度更宽裕 |
| 超额 | 停止上报或升 Plus（$39/月），个人用量预估月均 <1K traces，风险低 |

### 10.2 接入方案（无需 LangChain，langsmith SDK 官方支持裸 openai SDK 栈）

环境变量（.env 新增，全部可选，缺失即整体降级 no-op）：

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=deepfinresearch
```

代码改动面（比 §9 Helicone 方案多出的只是几个装饰器）：

| 位置 | 改动 |
|---|---|
| `app/config.py` | 新增可选 `langsmith_api_key / langsmith_project / langsmith_tracing`；有 Key 时设置对应 env（langsmith SDK 靠环境变量自启） |
| `app/llm/client.py` | `self._client = wrap_openai(OpenAI(...))`（`from langsmith.wrappers import wrap_openai`），一行；DeepSeek 返回 usage 字段，token 统计正常 |
| `app/pipeline/agent.py` | `answer()` 加 `@traceable(name="agent_answer", run_type="chain")`，metadata 带 session_id（chat_store 会话 id）；每次工具执行包一层 `@traceable(run_type="tool")` 或 `with trace(...)`，与现有 TraceStep 决策轨迹对应 |
| `app/pipeline/rag.py` | `answer()` 加 `@traceable`，检索步骤记 span（query/top-k/相似度），作为对照组 |
| CLI/脚本 | 短生命周期进程退出前 `langsmith` 客户端 flush（SDK 有后台队列，需确认 atexit 行为，PoC 验证项） |

无 Key/关闭开关时：`wrap_openai` 不注入（或 tracing=false），SDK 完全静默，234 个存量测试不受影响（单测 mock 层面验证降级路径）。

### 10.3 风险表（修订后）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 14 天 trace 保留，历史不可回溯 | 低（用户已接受） | 有价值的 bad case 及时加入 Dataset（不过期）；四期测评集本身落本地 git |
| 数据经 LangChain 云（美国），prompt 含知识库切片 | 中 | 个人投研数据非客户隐私，用户已接受云端；收紧时切本地 JSONL 兜底（§9.1 方案三） |
| SDK 侵入业务代码（装饰器），供应商锁定 | 低 | `@traceable` 仅标注函数边界，不改变逻辑；拆除 = 删装饰器 + env 置 false |
| smith.langchain.com 国内连通性 | 中 | PoC 第一步验证（上报走 HTTPS API，看板浏览器访问可能需代理） |
| 免费档 5K traces/月超额 | 低 | 预估月均 <1K；超额自动停报不断服务 |

### 10.4 PoC 步骤（修订后）

1. 注册 smith.langchain.com，建项目拿 API Key，验证国内连通性（看板 + API 上报）；
2. `uv pip install langsmith`，config.py 加可选配置（TDD：有/无 Key 的开关行为单测先行）；
3. client.py `wrap_openai` 一行接入，CLI 问一个问题，看板确认 generation 记录（model/tokens/延迟/完整 messages）；
4. agent.py 加 `@traceable`，验证 Run 树层级：answer → 每轮迭代 → 工具 span（参数/观察文本/耗时）；多轮对话验证 session 串联；
5. 用 LangSmith Dataset 建 3 条样本测评集，跑通 `evaluate()` 最小闭环，为四期后续步骤探路；
6. 记录 SDK 上报对端到端延迟的影响（异步批量，预期 <10ms）。

### 10.5 新增来源

- langsmith PyPI（pypi.org/project/langsmith）：`wrap_openai` + `@traceable` 官方用法，支持非 LangChain 栈
- flowhunt.io《2026 年 8 个最佳 LangChain 替代方案》：Developer 免费档 = 5,000 traces/月、14 天保留、1 席位
- pecollective.com《LangSmith Pricing》：Plus $39/席位/月、400 天保留（升级路径参照）
- tmtpost《LLM 可观测性平台大乱斗》：LangSmith 计量按 base trace、超额 $0.50/1k；框架绑定批评（本项目仅用 SDK 装饰器，不引入 LangChain，锁定面可控）
- CSDN《LangSmith 调试与综合项目实战》：DeepSeek + LangSmith 环境变量实践、usage 字段兼容性确认
