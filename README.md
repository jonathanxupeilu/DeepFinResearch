# DeepFinResearch

本地 RAG 智能问答助手（一期）。路线图：RAG 问答 → 工具调用/ReAct → 记忆 → 多Agent → PTC 财务计算。

## 快速开始
1. `python -m venv .venv && .venv/Scripts/activate`（Windows）
2. `pip install -e ".[dev]"`
3. `cp .env.example .env` 并填入 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`
4. `streamlit run app/ui/app.py`
- 终端问答：`python -m app.cli`

## 测试
- `pytest tests/unit tests/integration -v`（无需真实 Key）
- `pytest tests/e2e -m e2e -v`（需真实 Key）
