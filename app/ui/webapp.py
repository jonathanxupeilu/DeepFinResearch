import sys
from pathlib import Path

# streamlit run 会把本文件所在目录插到 sys.path 前面，
# 显式把项目根放到最前，保证 views 里 `import app` 解析到项目包
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from app.ui.views import advisor, monitor


def _advisor_home() -> None:
    advisor.render()


# 页面目录叫 views/ 而非 pages/：pages/ 是 Streamlit 魔法目录，冷启动直达
# /advisor 会绕过本入口、落到目录多页 fallback（advisor.py 独立执行 → 空白页）。
# 另外 st.navigation 强制默认页 url_path 为 ""（只挂根路径），故默认页用
# _advisor_home 包装，再注册隐藏别名页占住 "advisor" 路由，
# / 与 /advisor 都渲染投研顾问页。
st.navigation(
    {
        "投研顾问": [
            st.Page(_advisor_home, title="投研顾问", icon="💬", url_path="home"),
            st.Page(
                advisor.render,
                title="投研顾问",
                icon="💬",
                url_path="advisor",
                visibility="hidden",
            ),
        ],
        "市场监控": [
            st.Page(monitor.render, title="市场监控", icon="📊", url_path="monitor")
        ],
    }
).run()
