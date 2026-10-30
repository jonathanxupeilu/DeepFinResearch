# DeepFinResearch

本地 RAG 智能问答助手（一期）。路线图：RAG 问答 → 工具调用/ReAct → 记忆 → 多Agent → PTC 财务计算。

## 快速开始
1. `python -m venv .venv && .venv/Scripts/activate`（Windows）
2. `pip install -e ".[dev]"`
3. `cp .env.example .env` 并填入 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`
4. `streamlit run app/ui/webapp.py`
- 终端问答：`python -m app.cli`

## 测试
- `pytest tests/unit tests/integration -v`（无需真实 Key）
- `pytest tests/e2e -m e2e -v`（需真实 Key）

## 市场监控（二期）

「投研顾问」之外的第二页：基于 [akshare](https://github.com/akfamily/akshare) 的 6 维度市场信息**手动采集**与浏览（纯本地触发，无后台任务）。

### 功能
- **6 维度采集**：持仓公告 / 每日要闻 / 宏观指标 / 美联储 / 重大会议 / 行业指标
- **SQLite 本地存储**（`data/monitor.db`）：内容 hash 去重，重复采集不产生重复事件
- **单源失败隔离**：某一维度接口异常只在该维度报告中标记错误，不影响其余维度
- **入库知识库联动**：监控事件可一键转为文档入库，随后在投研顾问页提问即可检索引用

### 持仓配置
编辑 `config/holdings.json`（JSON 数组，`code` 为 6 位 A 股代码）：

```json
[
    {"code": "600519", "name": "贵州茅台"},
    {"code": "000858", "name": "五粮液"}
]
```

文件不存在时持仓公告维度无数据，其余维度不受影响。

### 手动采集用法
1. `streamlit run app/ui/webapp.py` → 左侧导航进入「市场监控」页
2. 点击「🔄 立即采集」→ 展示采集报告（各维度状态 / 新增条数 / 错误原因）
3. 顶部维度计数徽标查看累计事件数；事件列表支持按维度筛选，展开单条事件点「📥 入库知识库」
4. 回到「投研顾问」页即可就入库的事件内容提问（含来源引用）

