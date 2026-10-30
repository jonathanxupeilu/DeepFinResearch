import sys
from pathlib import Path

# streamlit run 会把本文件所在目录插到 sys.path 前面，
# 显式把项目根放到最前，保证 pages 里 `import app` 解析到项目包
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from app.ui.pages import advisor, monitor

st.navigation(
    {
        "投研顾问": [st.Page(advisor.render, title="投研顾问", icon="💬")],
        "市场监控": [st.Page(monitor.render, title="市场监控", icon="📊")],
    }
).run()
